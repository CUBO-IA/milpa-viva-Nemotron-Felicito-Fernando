"""Cifras agregadas de la simulación, calculadas con pandas (plan, sección 5, P6)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from milpa.simulate import leer_jsonl


def aplanar_run(ruta_jsonl) -> pd.DataFrame:
    """Convierte un run_{version}.jsonl válido en una tabla, una fila por persona."""
    filas = []
    for linea in leer_jsonl(ruta_jsonl):
        resp = linea.get("respuesta")
        valida = isinstance(resp, dict)
        filas.append({
            "uuid": linea["uuid"],
            "version": linea["version"],
            "department": linea["department"],
            "valida": valida,
            "decision": resp.get("decision") if valida else None,
            "entiende": resp.get("entiende") if valida else None,
            "barreras": resp.get("barreras", []) if valida else [],
            "respuesta_en_su_voz": resp.get("respuesta_en_su_voz") if valida else None,
            "fuente": linea.get("fuente"),
        })
    return pd.DataFrame(filas)


def _pct(serie: pd.Series) -> float:
    """Porcentaje con un decimal sobre las filas válidas; NaN si no hay filas."""
    if len(serie) == 0:
        return float("nan")
    return round(float(serie.mean()) * 100, 1)


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
