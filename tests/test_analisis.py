"""Pruebas de las cifras de P6 con datos sintéticos (sin LLM)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from milpa.analisis import (
    aplanar_run,
    barreras_frecuencia,
    citas_por_departamento,
    componentes_frecuencia,
    delta_por_departamento,
    metricas_por_grupo,
    tabla_por_depto,
)
from milpa.simulate import ruta_run


DEPTOS = [f"Depto{i:02d}" for i in range(14)]


def escribir_run(ruta: Path, version: str, filas_por_depto: int) -> None:
    """JSONL sintético: decisiones alternadas para que haya valores distintos."""
    with ruta.open("w", encoding="utf-8") as f:
        for d_idx, depto in enumerate(DEPTOS):
            for i in range(filas_por_depto):
                decision = ["adopta", "no_adopta", "lo_pensara"][(d_idx + i) % 3]
                linea = {
                    "uuid": f"{version}-{depto}-{i}",
                    "version": version,
                    "department": depto,
                    "respuesta": {
                        "entiende": "si" if i % 2 == 0 else "parcial",
                        "decision": decision,
                        "barreras": ["costo_inicial", "tramite_complejo"] if i else ["ninguna"],
                        "componentes": {"beneficio": "acepta", "copago": "rechaza" if i else "duda"},
                        "origen": {"beneficio": "llm", "copago": "regla" if i else "llm"},
                        "respuesta_en_su_voz": f"Voz {depto} {i}",
                    } if decision == "adopta" or i % 4 else "invalido",
                    "fuente": "local",
                }
                f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def test_summary_tiene_14_departamentos_y_n_suma_panel(tmp_path: Path) -> None:
    ruta = tmp_path / "run_A.jsonl"
    escribir_run(ruta, "A", filas_por_depto=20)
    df = aplanar_run(ruta)
    validas = df[df["valida"]]

    por_depto = metricas_por_grupo(validas, ["department"])
    assert len(por_depto) == 14
    total = len(df)
    assert total == 280
    assert int(por_depto["n"].sum()) == len(validas)


def test_adopcion_intencion_y_comprension_se_calculan_con_pandas(tmp_path: Path) -> None:
    filas = pd.DataFrame([
        {"uuid": "1", "department": "X", "valida": True, "decision": "adopta", "entiende": "si"},
        {"uuid": "2", "department": "X", "valida": True, "decision": "lo_pensara", "entiende": "no"},
        {"uuid": "3", "department": "X", "valida": True, "decision": "no_adopta", "entiende": "si"},
        {"uuid": "4", "department": "X", "valida": True, "decision": "no_adopta", "entiende": "parcial"},
    ])
    g = metricas_por_grupo(filas).iloc[0]
    assert g["n"] == 4
    assert g["adopcion_pct"] == 25.0
    assert g["intencion_pct"] == 50.0
    assert g["comprension_pct"] == 50.0


def test_barreras_y_citas_por_departamento(tmp_path: Path) -> None:
    ruta = tmp_path / "run_B.jsonl"
    escribir_run(ruta, "B", filas_por_depto=3)
    validas = aplanar_run(ruta)
    validas = validas[validas["valida"]]

    global_ = barreras_frecuencia(validas)
    assert global_[0]["personas"] >= global_[-1]["personas"]
    por_depto = barreras_frecuencia(validas, "department")
    assert set(por_depto) == set(DEPTOS)

    citas = citas_por_departamento(validas, k=2)
    assert all(len(v) <= 2 for v in citas.values())
    assert set(citas) <= set(DEPTOS)


def test_delta_b_menos_a_por_departamento(tmp_path: Path) -> None:
    a = pd.DataFrame([{"department": "X", "adopcion_pct": 40.0, "intencion_pct": 50.0, "comprension_pct": 60.0}])
    b = pd.DataFrame([{"department": "X", "adopcion_pct": 55.5, "intencion_pct": 45.0, "comprension_pct": 70.0}])
    delta = delta_por_departamento(a, b)
    assert delta == [{
        "department": "X",
        "delta_adopcion_pp": 15.5,
        "delta_intencion_pp": -5.0,
        "delta_comprension_pp": 10.0,
    }]


def test_ruta_run_usa_results() -> None:
    assert ruta_run("A").name == "run_A.jsonl"


def test_componentes_frecuencia_cuenta_reacciones(tmp_path: Path) -> None:
    ruta = tmp_path / "run_A.jsonl"
    escribir_run(ruta, "A", 4)
    df = aplanar_run(ruta)
    validas = df[df["valida"]]
    tabla = {f["componente"]: f for f in componentes_frecuencia(validas)}
    assert tabla["beneficio"]["acepta"] == len(validas)
    assert tabla["beneficio"]["por_regla"] == 0
    assert tabla["copago"]["por_regla"] == tabla["copago"]["rechaza"]
    assert tabla["copago"]["rechaza"] + tabla["copago"]["duda"] == len(validas)
    assert tabla["lenguaje"]["acepta"] == 0 and math.isnan(tabla["lenguaje"]["rechazo_pct"])


def test_aplanar_run_tolera_linea_incompleta_y_archivo_vacio(tmp_path: Path) -> None:
    ruta = tmp_path / "run_A.jsonl"
    escribir_run(ruta, "A", 1)
    with ruta.open("a", encoding="utf-8") as f:
        f.write('{"uuid": "a medio escribir')
    with pytest.raises(json.JSONDecodeError):
        aplanar_run(ruta)
    assert len(aplanar_run(ruta, tolerante=True)) == 14
    vacia = aplanar_run(tmp_path / "no_existe.jsonl")
    assert list(vacia.columns) and vacia.empty
    assert metricas_por_grupo(vacia[vacia["valida"]]).iloc[0]["n"] == 0


def test_tabla_por_depto_incluye_departamentos_sin_filas(tmp_path: Path) -> None:
    ruta = tmp_path / "run_A.jsonl"
    escribir_run(ruta, "A", 2)
    tabla = tabla_por_depto({"A": aplanar_run(ruta), "B": aplanar_run(tmp_path / "run_B.jsonl")},
                            DEPTOS + ["Sin filas"])
    sin = tabla[(tabla["department"] == "Sin filas") & (tabla["version"] == "A")].iloc[0]
    assert sin["n"] == 0 and math.isnan(sin["adopcion_pct"])
    assert tabla[tabla["version"] == "B"]["n"].sum() == 0
    assert tabla[tabla["version"] == "A"]["n"].sum() == 28
