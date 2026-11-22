"""Dashboard de Milpa Viva (plan, sección 5, P7-P8).

Modo precalculado: lee solo results/ y data/ (sin internet ni LLM).
Ejecutar: streamlit run app/dashboard.py
"""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

RESULTADOS = RAIZ / "results"
GEOJSON = RAIZ / "data" / "geo" / "slv_departamentos.geojson"
PANEL = RAIZ / "data" / "panel" / "panel.parquet"
ESCENARIO = "Escenario simulado para demo"
ETIQUETA_LOCAL = "Inferencia local: Nemotron en Radeon 880M"


def sin_tildes(texto: str) -> str:
    """Normaliza un nombre de departamento para unirlo con el GeoJSON."""
    base = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in base if not unicodedata.combining(c)).upper().strip()


@st.cache_data
def cargar_json(nombre: str) -> dict[str, Any] | None:
    """Lee un JSON de results/; None si aún no existe."""
    ruta = RESULTADOS / nombre
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


@st.cache_data
def cargar_run(version: str) -> pd.DataFrame:
    """Lee run_{version}.jsonl como tabla, una fila por persona."""
    from milpa.analisis import aplanar_run

    ruta = RESULTADOS / f"run_{version}.jsonl"
    return aplanar_run(ruta) if ruta.exists() else pd.DataFrame()


@st.cache_data
def cargar_panel() -> pd.DataFrame:
    """Perfil de cada persona del panel (para la tarjeta de detalle)."""
    return pd.read_parquet(PANEL) if PANEL.exists() else pd.DataFrame()


@st.cache_data
def cargar_geojson() -> dict[str, Any] | None:
    """GeoJSON de departamentos; None si la fuente no está en el repositorio."""
    if not GEOJSON.exists():
        return None
    geo = json.loads(GEOJSON.read_text(encoding="utf-8"))
    for feature in geo.get("features", []):
        props = feature.get("properties", {})
        props["nombre_norm"] = sin_tildes(props.get("name", ""))
    return geo


def mapa_adopcion(tabla: pd.DataFrame, titulo: str, escala: tuple[float, float]) -> Any:
    """Coropleta de adopción por departamento, sin mapa base."""
    geo = cargar_geojson()
    tabla = tabla.assign(nombre_norm=tabla["department"].map(sin_tildes))
    fig = px.choropleth(
        tabla,
        geojson=geo,
        locations="nombre_norm",
        featureidkey="properties.nombre_norm",
        color="adopcion_pct",
        range_color=escala,
        hover_name="department",
        color_continuous_scale="YlGn",
        title=titulo,
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), height=420)
    return fig


def servidor_activo() -> bool:
    """Indica si el servidor LLM responde; sin red bloqueante largo."""
    import urllib.request

    base = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    try:
        urllib.request.urlopen(f"{base}/models", timeout=2)
        return True
    except Exception:
        return False


AVISO_SIN_SERVIDOR = ("No se pudo completar la corrida en vivo. Revisa que el servidor LLM "
                      "esté activo y vuelve a intentarlo. Se siguen mostrando resultados precalculados.")


def lanzar_en_vivo(version: str, deptos: list[str]) -> tuple[bool, str, Path]:
    """Corre 05_run.py para los departamentos de demo en results/live_*.jsonl.

    Devuelve (ok, mensaje en español, ruta de salida). El detalle técnico no se muestra.
    """
    import subprocess
    from datetime import datetime

    salida = RESULTADOS / f"live_{version}_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    cmd = [sys.executable, str(RAIZ / "scripts" / "05_run.py"), "--version", version,
           "--deptos", *deptos, "--out", str(salida)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=RAIZ, timeout=1800)
    except (OSError, subprocess.TimeoutExpired):
        return False, AVISO_SIN_SERVIDOR, salida
    if proc.returncode != 0:
        return False, AVISO_SIN_SERVIDOR, salida
    return True, f"Listo: {salida.name}", salida


def ultimo_en_vivo(version: str) -> Path | None:
    """Archivo live_{version}_*.jsonl más reciente, o None si no hay ninguno."""
    archivos = sorted(RESULTADOS.glob(f"live_{version}_*.jsonl"))
    return archivos[-1] if archivos else None


def resumen_en_vivo(ruta: Path) -> pd.DataFrame:
    """Una fila por llamada del JSONL en vivo: duración en segundos y backend usado."""
    from milpa.simulate import leer_jsonl

    filas = []
    for r in leer_jsonl(ruta):
        m = r.get("metricas", {})
        filas.append({
            "uuid": r.get("uuid"),
            "departamento": r.get("department"),
            "versión": r.get("version"),
            "segundos": m.get("tiempo_s"),
            "backend": m.get("backend"),
        })
    return pd.DataFrame(filas, columns=["uuid", "departamento", "versión", "segundos", "backend"])


def nombre_de(uuid: str) -> str:
    """Nombre de display de una persona del panel, o su uuid si no se encuentra."""
    panel = cargar_panel()
    fila = panel.loc[panel["uuid"] == uuid, "nombre_display"] if not panel.empty else []
    return str(fila.iloc[0]) if len(fila) else str(uuid)


def respuesta_de(version: str, uuid: str) -> dict[str, Any] | None:
    """Fila de run_{version}.jsonl para una persona, con mensajes y respuesta completa."""
    from milpa.simulate import leer_jsonl

    for linea in leer_jsonl(RESULTADOS / f"run_{version}.jsonl"):
        if linea.get("uuid") == uuid:
            return linea
    return None


def detalle_agricultor(uuid: str, version: str) -> None:
    """Tarjeta de una persona: perfil, mensajes recibidos y respuesta; A y B lado a lado si existen."""
    panel = cargar_panel()
    perfil = panel.loc[panel["uuid"] == uuid]
    if not perfil.empty:
        p = perfil.iloc[0]
        st.markdown(f"**{p['nombre_display']}**, {p['age']} años, {p['municipality']} ({p['department']}). "
                    f"{p['occupation']}; cultivo principal: {p['cultivo_principal']} ({p['escala']}).")
    versiones = [v for v in ("A", "B") if version in ("A vs B", v)]
    lineas = {v: respuesta_de(v, uuid) for v in versiones}
    base = next((x for x in lineas.values() if x), None)
    if base is None:
        st.info("Esta persona aún no tiene respuesta registrada para esta versión.")
        return
    st.markdown("**Mensajes recibidos**")
    st.markdown(f"- Clima: {base['mensajes'].get('clima', '')}")
    st.markdown(f"- Precios: {base['mensajes'].get('mercado', '')}")
    columnas = st.columns(len(versiones))
    for col, v in zip(columnas, versiones):
        linea = lineas[v]
        with col:
            st.markdown(f"**Versión {v}**")
            if not linea or linea["respuesta"] == "invalido":
                st.warning("Respuesta inválida tras reintento.")
                continue
            resp = linea["respuesta"]
            st.markdown(f"> {resp.get('respuesta_en_su_voz', '')}")
            st.markdown(f"Decisión: **{resp.get('decision', '')}** "
                        f"({resp.get('probabilidad_adopcion', '')} %) · Entiende: {resp.get('entiende', '')}")
            componentes = resp.get("componentes", {})
            if componentes:
                origen = resp.get("origen", {})
                st.markdown("Componentes: " + " · ".join(
                    f"{c}: {r}" + (" (regla)" if origen.get(c) == "regla" else "")
                    for c, r in componentes.items()))
            st.markdown("Barreras: " + (", ".join(resp.get("barreras", [])) or "ninguna"))
            if resp.get("pregunta_que_haria"):
                st.markdown(f"Pregunta: *{resp['pregunta_que_haria']}*")


def pagina() -> None:
    """Dibuja el dashboard completo a partir de archivos precalculados."""
    st.set_page_config(page_title="Milpa Viva", layout="wide")
    st.title("Milpa Viva: simulación del programa A y B")
    st.caption(ESCENARIO)

    with st.sidebar:
        st.header("Controles")
        version = st.selectbox("Versión", ["A", "B", "A vs B"])
        st.write("Escenario:", ESCENARIO)
        vivo = servidor_activo()
        if st.button("Correr en vivo (Morazán, La Unión)", disabled=not vivo):
            ok, mensaje, _ = lanzar_en_vivo("B" if version == "A vs B" else version,
                                            ["Morazán", "La Unión"])
            st.success(mensaje) if ok else st.error(mensaje)
        if not vivo:
            st.info("Servidor LLM no disponible: el modo en vivo está desactivado. "
                    "Se muestran resultados precalculados.")
        else:
            st.caption(ETIQUETA_LOCAL if "localhost" in os.environ.get("LLM_BASE_URL", "") else "")

    clave = "AB" if version == "A vs B" else version
    version_vivo = "B" if version == "A vs B" else version
    archivo_vivo = ultimo_en_vivo(version_vivo)
    if archivo_vivo is not None:
        st.subheader(f"Corrida en vivo: {archivo_vivo.name}")
        tabla_vivo = resumen_en_vivo(archivo_vivo)
        st.dataframe(tabla_vivo, use_container_width=True)

    ab = cargar_json("summary_AB.json")
    if ab is None:
        st.warning("Aún no hay summary_AB.json. Corre scripts/06_analyze.py.")
        return
    g = ab["global"]
    cols = st.columns(5)
    cols[0].metric("Adopción", f"{g.get('adopcion_pct', 0):.1f}%")
    cols[1].metric("Intención", f"{g.get('intencion_media', 0):.2f}")
    cols[2].metric("Comprensión", f"{g.get('comprension_media', 0):.2f}")
    cols[3].metric("Personas (n)", g.get("n", 0))
    cols[4].metric("Delta B-A (adopción)", f"{g.get('delta_adopcion_pp', 0):+.1f} pp")

    resumen = cargar_json(f"summary_{clave}.json") or {}
    por_depto = pd.DataFrame(resumen.get("por_departamento", []))
    if not por_depto.empty and "adopcion_pct" in por_depto.columns:
        escala = (0.0, 100.0)
        if version == "A vs B":
            c1, c2 = st.columns(2)
            for col, v in ((c1, "A"), (c2, "B")):
                datos = cargar_json(f"summary_{v}.json") or {}
                tabla = pd.DataFrame(datos.get("por_departamento", []))
                if not tabla.empty:
                    col.plotly_chart(mapa_adopcion(tabla, f"Adopción {v}", escala), use_container_width=True)
        else:
            st.plotly_chart(mapa_adopcion(por_depto, f"Adopción {version}", escala), use_container_width=True)
        st.subheader("Departamentos")
        st.dataframe(por_depto, use_container_width=True)

    st.subheader("Reacción por componente del programa")
    for v in (["A", "B"] if version == "A vs B" else [version]):
        datos = cargar_json(f"summary_{v}.json") or {}
        comp = pd.DataFrame(datos.get("componentes_global", []))
        if not comp.empty:
            largo = comp.melt(id_vars="componente", value_vars=["acepta", "duda", "rechaza"],
                              var_name="reacción", value_name="personas")
            st.plotly_chart(px.bar(largo, x="componente", y="personas", color="reacción",
                                   title=f"Componentes {v}"), use_container_width=True)

    st.subheader("Barreras principales")
    for v in (["A", "B"] if version == "A vs B" else [version]):
        datos = cargar_json(f"summary_{v}.json") or {}
        barreras = pd.DataFrame(datos.get("barreras_global", []))
        if not barreras.empty:
            st.plotly_chart(px.bar(barreras, x="barrera", y="personas", title=f"Barreras {v}"),
                            use_container_width=True)

    analisis = cargar_json(f"analisis_{clave}.json")
    st.subheader("Analista")
    if analisis:
        st.write(analisis.get("resumen_ejecutivo", ""))
        for d in analisis.get("departamentos_criticos", []):
            st.markdown(f"**{d['departamento']}** ({d['barrera_principal']}): {d['explicacion']}")
        for r in analisis.get("recomendaciones", []):
            st.markdown(f"- {r['accion']} (ataca: {r['barrera_que_ataca']})")
    else:
        st.info("Sin análisis del Analista todavía.")

    st.subheader("Detalle de agricultor")
    tabla = cargar_run("A")
    if tabla.empty:
        st.info("Sin resultados de simulación para esta versión.")
        return
    deptos = sorted(tabla["department"].dropna().unique())
    depto = st.selectbox("Departamento", ["Todos"] + deptos)
    buscar = st.text_input("Buscar por nombre")
    uuid_url = st.query_params.get("uuid")
    if depto != "Todos":
        tabla = tabla[tabla["department"] == depto]
    if buscar:
        panel = cargar_panel()
        if not panel.empty and "nombre_display" in panel.columns:
            uuids = panel.loc[panel["nombre_display"].str.contains(buscar, case=False, na=False), "uuid"]
            tabla = tabla[tabla["uuid"].isin(uuids)]
    if uuid_url:
        tabla = tabla[tabla["uuid"] == uuid_url] if uuid_url in set(tabla["uuid"]) else tabla
    if tabla.empty:
        st.info("Ninguna persona coincide con el filtro.")
        return
    persona = st.selectbox("Persona", tabla["uuid"].tolist(), format_func=lambda u: nombre_de(u))
    detalle_agricultor(persona, version)


if __name__ == "__main__":
    pagina()
