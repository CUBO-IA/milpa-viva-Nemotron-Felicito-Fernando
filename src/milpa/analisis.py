"""Cifras agregadas de la simulación, calculadas con pandas (plan, sección 5, P6)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from milpa.schemas import COMPONENTES
from milpa.simulate import leer_jsonl

REACCIONES = ("acepta", "duda", "rechaza")
COLUMNAS = ["uuid", "version", "department", "valida", "decision", "probabilidad_adopcion",
            "componentes", "origen", "entiende", "barreras", "respuesta_en_su_voz", "fuente"]


def aplanar_run(ruta_jsonl, tolerante: bool = False) -> pd.DataFrame:
    """Convierte un run_{version}.jsonl en una tabla, una fila por persona.

    Siempre devuelve las columnas de COLUMNAS, aunque el archivo esté vacío o no
    exista. Con `tolerante=True` omite líneas incompletas (corrida en curso).
    """
    filas = []
    for linea in leer_jsonl(ruta_jsonl, tolerante=tolerante):
        resp = linea.get("respuesta")
        valida = isinstance(resp, dict)
        filas.append({
            "uuid": linea["uuid"],
            "version": linea["version"],
            "department": linea["department"],
            "valida": valida,
            "decision": resp.get("decision") if valida else None,
            "probabilidad_adopcion": resp.get("probabilidad_adopcion") if valida else None,
            "componentes": resp.get("componentes", {}) if valida else {},
            "origen": resp.get("origen", {}) if valida else {},
            "entiende": resp.get("entiende") if valida else None,
            "barreras": resp.get("barreras", []) if valida else [],
            "respuesta_en_su_voz": resp.get("respuesta_en_su_voz") if valida else None,
            "fuente": linea.get("fuente"),
        })
    df = pd.DataFrame(filas, columns=COLUMNAS)
    # dtype bool explícito: con la tabla vacía, df[df["valida"]] seleccionaría columnas.
    return df.astype({"valida": bool})


def _pct(serie: pd.Series) -> float:
    """Porcentaje con un decimal sobre las filas válidas; NaN si no hay filas."""
    if len(serie) == 0:
        return float("nan")
    return round(float(serie.mean()) * 100, 1)


def tabla_por_depto(
    tablas: dict[str, pd.DataFrame], deptos: list[str] | None = None,
) -> pd.DataFrame:
    """n, inválidas, adopción, intención y comprensión por departamento y versión.

    `tablas` es {versión: salida de aplanar_run}. Los departamentos de `deptos` sin
    filas aparecen con n=0 y porcentajes NaN, para ver el avance de una corrida parcial.
    """
    filas = []
    todos = sorted(set(deptos or []).union(*(set(t["department"].dropna()) for t in tablas.values())))
    for version, df in tablas.items():
        for depto in todos:
            grupo = df[df["department"] == depto]
            validas = grupo[grupo["valida"]]
            m = metricas_por_grupo(validas).iloc[0]
            filas.append({
                "department": depto, "version": version, "n": len(grupo),
                "validas": len(validas), "invalidas": len(grupo) - len(validas),
                "adopcion_pct": m["adopcion_pct"], "intencion_pct": m["intencion_pct"],
                "comprension_pct": m["comprension_pct"],
            })
    return pd.DataFrame(filas, columns=["department", "version", "n", "validas", "invalidas",
                                        "adopcion_pct", "intencion_pct", "comprension_pct"])


def metricas_por_grupo(validas: pd.DataFrame, por: list[str] | None = None) -> pd.DataFrame:
    """Adopción, intención, comprensión y n, global o por grupo."""
    base = validas.assign(
        adopta=validas["decision"].eq("adopta"),
        intencion=validas["decision"].isin(["adopta", "lo_pensara"]),
        comprende=validas["entiende"].eq("si"),
    )
    if not por:
        return pd.DataFrame([{
            "n": len(base),
            "adopcion_pct": _pct(base["adopta"]),
            "intencion_pct": _pct(base["intencion"]),
            "comprension_pct": _pct(base["comprende"]),
        }])
    grupos = base.groupby(por, sort=True)
    return grupos.agg(
        n=("uuid", "size"),
        adopcion_pct=("adopta", lambda s: _pct(s)),
        intencion_pct=("intencion", lambda s: _pct(s)),
        comprension_pct=("comprende", lambda s: _pct(s)),
    ).reset_index()


def barreras_frecuencia(validas: pd.DataFrame, por: str | None = None) -> list[dict[str, Any]] | dict[str, list[dict[str, Any]]]:
    """Conteo de barreras (una persona puede tener hasta 3), global o por departamento."""
    def conteo(df: pd.DataFrame) -> list[dict[str, Any]]:
        filas = df[["barreras"]].explode("barreras").dropna()
        cuenta = filas["barreras"].value_counts()
        return [{"barrera": b, "personas": int(c)} for b, c in cuenta.items()]

    if por is None:
        return conteo(validas)
    return {str(depto): conteo(grupo) for depto, grupo in validas.groupby(por, sort=True)}


def componentes_frecuencia(validas: pd.DataFrame) -> list[dict[str, Any]]:
    """Por componente: personas que aceptan, dudan o rechazan, % de rechazo y cuántas
    reacciones finales vinieron de la regla estructural (`por_regla`)."""
    salida = []
    for c in COMPONENTES:
        valores = validas["componentes"].map(lambda d, c=c: (d or {}).get(c))
        cuenta = {r: int(valores.eq(r).sum()) for r in REACCIONES}
        n = sum(cuenta.values())
        origen = validas["origen"].map(lambda d, c=c: (d or {}).get(c)) if "origen" in validas else pd.Series(dtype=object)
        salida.append({"componente": c, **cuenta, "por_regla": int(origen.eq("regla").sum()),
                       "rechazo_pct": round(100 * cuenta["rechaza"] / n, 1) if n else float("nan")})
    return salida


def citas_por_departamento(validas: pd.DataFrame, k: int = 2) -> dict[str, list[str]]:
    """Hasta k respuestas en su voz por departamento, en orden del archivo."""
    con_voz = validas[validas["respuesta_en_su_voz"].notna()]
    return {
        str(depto): grupo["respuesta_en_su_voz"].head(k).tolist()
        for depto, grupo in con_voz.groupby("department", sort=True)
    }


def delta_por_departamento(
    tabla_a: pd.DataFrame, tabla_b: pd.DataFrame
) -> list[dict[str, Any]]:
    """Diferencia B menos A por departamento en adopción, intención y comprensión."""
    m = tabla_a.merge(tabla_b, on="department", suffixes=("_A", "_B"))
    salida = []
    for _, r in m.iterrows():
        salida.append({
            "department": r["department"],
            "delta_adopcion_pp": round(r["adopcion_pct_B"] - r["adopcion_pct_A"], 1),
            "delta_intencion_pp": round(r["intencion_pct_B"] - r["intencion_pct_A"], 1),
            "delta_comprension_pp": round(r["comprension_pct_B"] - r["comprension_pct_A"], 1),
        })
    return salida
