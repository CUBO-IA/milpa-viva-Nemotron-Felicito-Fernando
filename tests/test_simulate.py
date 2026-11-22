"""Pruebas de la simulación con funciones falsas (sin LLM)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from milpa.simulate import (
    clave_segmento,
    completar_cache,
    correr_version,
    elegir_por_depto,
    uuids_escritos,
)


def panel_sintetico() -> pd.DataFrame:
    filas = []
    for depto, zona in [("Morazán", "Oriental"), ("La Unión", "Oriental"), ("Ahuachapán", "Occidental")]:
        for i in range(5):
            filas.append({
                "uuid": f"{depto[:3]}-{i}", "department": depto, "municipality": "M",
                "zona": zona, "cultivo_principal": "granos_basicos", "escala": "subsistencia",
                "nombre_display": f"P{i}", "age": 40, "sex": "Hombre", "area": "rural",
                "occupation": "Cultivo de cereales", "education_level": "primaria",
                "household_type": "x", "marital_status": "x",
                "persona": "Vive en una parcela pequeña.", "professional_persona": "Agricultor.",
            })
    return pd.DataFrame(filas)


def clima_falso(depto, zona, cultivo, escala, seed):
    return SimpleNamespace(model_dump=lambda: {"mensaje_corto": "c"}), {"backend": "local"}


def mercado_falso(depto, cultivo, escala, seed):
    return SimpleNamespace(model_dump=lambda: {"mensaje_corto": "m"}), {"backend": "local"}


def reaccion_falsa(perfil, mensaje_clima, mensaje_mercado, version, seed=None):
    obj = SimpleNamespace(model_dump=lambda: {"decision": "adopta"})
    return obj, {"backend": "local", "latencia_s": 0.01}


def test_elegir_por_depto_toma_n_por_departamento() -> None:
    elegidas = elegir_por_depto(panel_sintetico(), 2, 42, ["Morazán", "La Unión"])
    assert len(elegidas) == 4
    assert elegidas["department"].value_counts().to_dict() == {"Morazán": 2, "La Unión": 2}


def test_resume_no_duplica_lineas(tmp_path: Path) -> None:
    personas = elegir_por_depto(panel_sintetico(), 2, 42, ["Morazán"])
    ruta = tmp_path / "run_A.jsonl"
    cache = {clave_segmento("Morazán", "granos_basicos", "subsistencia"):
             {"clima": {"mensaje_corto": "c"}, "mercado": {"mensaje_corto": "m"}}}

    primera = correr_version(personas.iloc[:1], "A", cache, reaccion_falsa, 42, ruta, progreso=lambda _: None)
    segunda = correr_version(personas, "A", cache, reaccion_falsa, 42, ruta, progreso=lambda _: None)

    assert primera["nuevas"] == 1
    assert segunda["ya_existian"] == 1 and segunda["nuevas"] == 1
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2
    assert len(uuids_escritos(ruta)) == 2


def test_respuesta_invalida_se_cuenta_y_se_marca(tmp_path: Path) -> None:
    personas = elegir_por_depto(panel_sintetico(), 1, 42, ["Morazán"])
    ruta = tmp_path / "run_B.jsonl"
    cache = {clave_segmento("Morazán", "granos_basicos", "subsistencia"):
             {"clima": None, "mercado": None}}

    def sin_objeto(*args, **kwargs):
        return None, {"backend": "local", "error": "json"}

    resumen = correr_version(personas, "B", cache, sin_objeto, 42, ruta, progreso=lambda _: None)
    assert resumen["invalidas"] == 1 and resumen["validas"] == 0
    linea = json.loads(ruta.read_text(encoding="utf-8"))
    assert linea["respuesta"] == "invalido"


def test_cache_se_calcula_una_vez_por_segmento(tmp_path: Path) -> None:
    personas = panel_sintetico()
    llamadas: list[str] = []

    def calcular(seg):
        llamadas.append(seg["departamento"])
        return {"clima": {"mensaje_corto": "c"}, "mercado": {"mensaje_corto": "m"}}

    ruta = tmp_path / "cache_segmentos.json"
    completar_cache(personas, ruta, calcular)
    completar_cache(personas, ruta, calcular)

    # Tres departamentos, un segmento cada uno (mismo cultivo y escala).
    assert sorted(llamadas) == ["Ahuachapán", "La Unión", "Morazán"]
    assert len(json.loads(ruta.read_text(encoding="utf-8"))) == 3
