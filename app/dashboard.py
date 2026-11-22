"""Dashboard de Milpa Viva (plan, sección 5, P7-P8).

Lee solo results/ y data/ (sin internet ni LLM). Las cifras se calculan en cada
recarga directamente desde results/run_A.jsonl y run_B.jsonl, así que funciona
con corridas parciales o en curso. Los análisis del Analista
(results/analisis_*.json) son opcionales.
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

# MILPA_RESULTADOS permite apuntar a otra carpeta (pruebas).
RESULTADOS = Path(os.environ.get("MILPA_RESULTADOS", RAIZ / "results"))
GEOJSON = RAIZ / "data" / "geo" / "slv_departamentos.geojson"
PANEL = RAIZ / "data" / "panel" / "panel.parquet"
ESCENARIO = "Escenario simulado para demo"
ETIQUETA_LOCAL = "Inferencia local: Nemotron en Radeon 880M"


def sin_tildes(texto: str) -> str:
    """Normaliza un nombre de departamento para unirlo con el GeoJSON."""
    base = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in base if not unicodedata.combining(c)).upper().strip()


@st.cache_data
def _cargar_json(nombre: str, huella: tuple[int, int]) -> dict[str, Any] | None:
    ruta = RESULTADOS / nombre
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def cargar_json(nombre: str) -> dict[str, Any] | None:
    """Lee un JSON de results/; None si aún no existe. Se relee si el archivo cambia."""
    return _cargar_json(nombre, firma(RESULTADOS / nombre))


def firma(ruta: Path) -> tuple[int, int]:
    """(mtime, tamaño) del archivo; cambia cuando una corrida agrega filas."""
    if not ruta.exists():
        return (0, 0)
    st_ = ruta.stat()
    return (st_.st_mtime_ns, st_.st_size)


@st.cache_data
# `huella` (mtime, tamaño) forma parte de la clave de caché: sin guion bajo inicial,
# porque st.cache_data no hashea los parámetros que empiezan con "_".
def _cargar_run(version: str, huella: tuple[int, int]) -> pd.DataFrame:
    from milpa.analisis import aplanar_run

    return aplanar_run(RESULTADOS / f"run_{version}.jsonl", tolerante=True)


def cargar_run(version: str) -> pd.DataFrame:
    """run_{version}.jsonl como tabla; se relee cuando el archivo crece.

    Tolera la última línea a medio escribir y devuelve una tabla vacía (con
    columnas) si el archivo aún no existe.
    """
    return _cargar_run(version, firma(RESULTADOS / f"run_{version}.jsonl"))


def esperadas_por_version() -> int:
    """Personas que tendrá una corrida completa: por_depto × departamentos del panel."""
    from milpa.config import load_config

    panel = cargar_panel()
    deptos = panel["department"].nunique() if not panel.empty else 14
    return int(load_config()["panel"]["por_depto"]) * deptos


def deptos_del_panel() -> list[str]:
    """Los departamentos del panel, para mostrar también los que aún no tienen filas."""
    panel = cargar_panel()
    return sorted(panel["department"].dropna().unique()) if not panel.empty else []


SEGUNDOS_CORRIDA_ACTIVA = 300


def corrida_en_curso() -> bool:
    """True si algún run_*.jsonl se modificó hace menos de 5 minutos."""
    import time

    ahora = time.time()
    return any(ahora - r.stat().st_mtime < SEGUNDOS_CORRIDA_ACTIVA
               for r in RESULTADOS.glob("run_*.jsonl"))


def pct(valor: Any) -> str:
    """Porcentaje con un decimal, o "—" si no hay datos."""
    return "—" if valor is None or pd.isna(valor) else f"{float(valor):.1f}%"


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
    """Coropleta de adopción por departamento, sin mapa base (None si no hay GeoJSON)."""
    geo = cargar_geojson()
    if geo is None:
        return None
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
    for r in leer_jsonl(ruta, tolerante=True):
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

    for linea in leer_jsonl(RESULTADOS / f"run_{version}.jsonl", tolerante=True):
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


def seccion_avance(tablas: dict[str, pd.DataFrame]) -> None:
    """Filas escritas, inválidas y avance contra la corrida completa, por versión."""
    esperadas = esperadas_por_version()
    cols = st.columns(len(tablas))
    for col, (v, df) in zip(cols, tablas.items()):
        n, invalidas = len(df), int((~df["valida"]).sum())
        with col:
            st.markdown(f"**Versión {v}**: {n} de {esperadas} personas")
            st.progress(min(n / esperadas, 1.0) if esperadas else 0.0)
            st.caption(f"Inválidas: {invalidas} ({pct(100 * invalidas / n if n else None)})")


def seccion_kpis(tablas: dict[str, pd.DataFrame]) -> dict[str, dict[str, float]]:
    """Adopción, intención y comprensión con las filas válidas que haya, por versión."""
    from milpa.analisis import metricas_por_grupo

    globales = {}
    for v, df in tablas.items():
        globales[v] = metricas_por_grupo(df[df["valida"]]).iloc[0].to_dict()
    cols = st.columns(len(tablas) * 2 + (1 if len(tablas) == 2 else 0))
    k = 0
    for v, g in globales.items():
        cols[k].metric(f"Adopción {v}", pct(g["adopcion_pct"]), help=f"n válidas = {int(g['n'])}")
        cols[k + 1].metric(f"Intención {v}", pct(g["intencion_pct"]),
                           help="adopta o lo pensaría")
        k += 2
    if len(globales) == 2:
        a, b = globales["A"]["adopcion_pct"], globales["B"]["adopcion_pct"]
        delta = "—" if pd.isna(a) or pd.isna(b) else f"{b - a:+.1f} pp"
        cols[k].metric("Delta B−A (adopción)", delta)
    return globales


def seccion_departamentos(tablas: dict[str, pd.DataFrame], version: str) -> None:
    """n y adopción por departamento y versión; incluye departamentos sin filas."""
    from milpa.analisis import tabla_por_depto

    larga = tabla_por_depto(tablas, deptos_del_panel())
    if larga.empty:
        return
    ancha = larga.pivot(index="department", columns="version",
                        values=["n", "invalidas", "adopcion_pct", "intencion_pct"])
    ancha.columns = [f"{m}_{v}" for m, v in ancha.columns]
    ancha = ancha.reset_index()
    enteros = [c for c in ancha.columns if c.startswith(("n_", "invalidas_"))]
    ancha[enteros] = ancha[enteros].astype("Int64")
    if {"adopcion_pct_A", "adopcion_pct_B"} <= set(ancha.columns):
        ancha["delta_adopcion_pp"] = (ancha["adopcion_pct_B"] - ancha["adopcion_pct_A"]).round(1)
    st.subheader("Departamentos")
    st.caption("n = personas con fila escrita en la corrida; los porcentajes usan solo filas válidas. "
               "Un departamento sin filas aparece con n = 0 y sin porcentaje.")
    st.dataframe(ancha, width="stretch", hide_index=True)

    escala = (0.0, 100.0)
    versiones = list(tablas) if version == "A vs B" else [version]
    cols = st.columns(len(versiones))
    for col, v in zip(cols, versiones):
        datos = larga[larga["version"] == v]
        fig = mapa_adopcion(datos, f"Adopción {v}", escala)
        if fig is not None:
            col.plotly_chart(fig, width="stretch")


def seccion_componentes_y_barreras(tablas: dict[str, pd.DataFrame], version: str) -> None:
    """Reacción por componente y barreras, calculadas desde las filas válidas."""
    from milpa.analisis import barreras_frecuencia, componentes_frecuencia

    versiones = list(tablas) if version == "A vs B" else [version]
    st.subheader("Reacción por componente del programa")
    cols = st.columns(len(versiones))
    for col, v in zip(cols, versiones):
        validas = tablas[v][tablas[v]["valida"]]
        if validas.empty:
            col.info(f"Versión {v}: aún sin filas válidas.")
            continue
        comp = pd.DataFrame(componentes_frecuencia(validas))
        largo = comp.melt(id_vars="componente", value_vars=["acepta", "duda", "rechaza"],
                          var_name="reacción", value_name="personas")
        col.plotly_chart(px.bar(largo, x="componente", y="personas", color="reacción",
                                title=f"Componentes {v} (n={len(validas)})"),
                         width="stretch")

    st.subheader("Barreras principales")
    cols = st.columns(len(versiones))
    for col, v in zip(cols, versiones):
        barreras = pd.DataFrame(barreras_frecuencia(tablas[v][tablas[v]["valida"]]))
        if barreras.empty:
            col.info(f"Versión {v}: sin barreras registradas todavía.")
            continue
        col.plotly_chart(px.bar(barreras, x="barrera", y="personas", title=f"Barreras {v}"),
                         width="stretch")


def pagina() -> None:
    """Dibuja el dashboard calculando las cifras desde los JSONL disponibles."""
    st.set_page_config(page_title="Milpa Viva", layout="wide")
    st.title("Milpa Viva: simulación del programa A y B")
    st.caption(ESCENARIO)

    with st.sidebar:
        st.header("Controles")
        version = st.selectbox("Versión", ["A", "B", "A vs B"])
        if st.button("Actualizar con las filas nuevas"):
            st.rerun()
        st.write("Escenario:", ESCENARIO)
        vivo = servidor_activo()
        ocupado = corrida_en_curso()
        if st.button("Correr en vivo (Morazán, La Unión)", disabled=not vivo or ocupado):
            ok, mensaje, _ = lanzar_en_vivo("B" if version == "A vs B" else version,
                                            ["Morazán", "La Unión"])
            st.success(mensaje) if ok else st.error(mensaje)
        if ocupado:
            st.info("Hay una corrida escribiendo en results/run_*.jsonl: el modo en vivo "
                    "está desactivado para no competir por el modelo.")
        elif not vivo:
            st.info("Servidor LLM no disponible: el modo en vivo está desactivado. "
                    "Se muestran los resultados guardados.")
        else:
            st.caption(ETIQUETA_LOCAL if "localhost" in os.environ.get("LLM_BASE_URL", "") else "")

    clave = "AB" if version == "A vs B" else version
    version_vivo = "B" if version == "A vs B" else version
    archivo_vivo = ultimo_en_vivo(version_vivo)
    if archivo_vivo is not None:
        st.subheader(f"Corrida en vivo: {archivo_vivo.name}")
        st.dataframe(resumen_en_vivo(archivo_vivo), width="stretch")

    todas = {v: cargar_run(v) for v in ("A", "B")}
    if all(df.empty for df in todas.values()):
        st.warning("Aún no hay filas en results/run_A.jsonl ni run_B.jsonl. Corre scripts/05_run.py.")
        return
    tablas = todas if version == "A vs B" else {version: todas[version]}

    st.subheader("Avance de las corridas")
    seccion_avance(todas)
    if any(len(df) < esperadas_por_version() for df in todas.values()):
        st.caption("Resultados parciales: las cifras usan solo las filas escritas hasta ahora.")
    seccion_kpis(tablas)
    seccion_departamentos(tablas, version)
    seccion_componentes_y_barreras(tablas, version)

    analisis = cargar_json(f"analisis_{clave}.json")
    st.subheader("Analista")
    if analisis:
        st.caption("Redactado por scripts/06_analyze.py; puede corresponder a una corrida anterior.")
        st.write(analisis.get("resumen_ejecutivo", ""))
        for d in analisis.get("departamentos_criticos", []):
            st.markdown(f"**{d['departamento']}** ({d['barrera_principal']}): {d['explicacion']}")
        for r in analisis.get("recomendaciones", []):
            st.markdown(f"- {r['accion']} (ataca: {r['barrera_que_ataca']})")
    else:
        st.info("Sin análisis del Analista todavía (se genera con scripts/06_analyze.py al terminar).")

    st.subheader("Detalle de agricultor")
    tabla = pd.concat([df for df in tablas.values() if not df.empty], ignore_index=True)
    if tabla.empty:
        st.info("Sin resultados de simulación para esta versión.")
        return
    tabla = tabla.drop_duplicates("uuid")
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
