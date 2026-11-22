"""Pruebas de la simulación con funciones falsas (sin LLM)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from milpa.simulate import (
    ErrorSegmento,
    clave_clima,
    clave_mercado,
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


def objeto(mensaje: str) -> SimpleNamespace:
    return SimpleNamespace(model_dump=lambda: {"mensaje_corto": mensaje})


def cache_valida() -> dict:
    return {
        "clima": {clave_clima("Oriental", "granos_basicos"): {"respuesta": {"mensaje_corto": "c"}}},
        "mercado": {clave_mercado("granos_basicos", "subsistencia"): {"respuesta": {"mensaje_corto": "m"}}},
    }


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
    cache = cache_valida()

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
    cache = cache_valida()

    def sin_objeto(*args, **kwargs):
        return None, {"backend": "local", "error": "json"}

    resumen = correr_version(personas, "B", cache, sin_objeto, 42, ruta, progreso=lambda _: None)
    assert resumen["invalidas"] == 1 and resumen["validas"] == 0
    linea = json.loads(ruta.read_text(encoding="utf-8"))
    assert linea["respuesta"] == "invalido"
    assert linea["mensajes"] == {"clima": "c", "mercado": "m"}


def test_cache_se_calcula_una_vez_por_segmento(tmp_path: Path) -> None:
    personas = panel_sintetico()
    llamadas: list[tuple[str, ...]] = []

    def clima(zona, cultivo):
        llamadas.append(("clima", zona, cultivo))
        return objeto("c"), {}

    def mercado(cultivo, escala):
        llamadas.append(("mercado", cultivo, escala))
        return objeto("m"), {}

    ruta = tmp_path / "cache_segmentos.json"
    completar_cache(personas, ruta, clima, mercado, progreso=lambda _: None)
    completar_cache(personas, ruta, clima, mercado, progreso=lambda _: None)

    # Clima por zona (dos zonas) y Mercado por cultivo × escala (uno), no por departamento.
    assert sorted(llamadas) == [
        ("clima", "Occidental", "granos_basicos"),
        ("clima", "Oriental", "granos_basicos"),
        ("mercado", "granos_basicos", "subsistencia"),
    ]
    cache = json.loads(ruta.read_text(encoding="utf-8"))
    assert len(cache["clima"]) == 2 and len(cache["mercado"]) == 1


def test_cache_recalcula_segmentos_en_none(tmp_path: Path) -> None:
    ruta = tmp_path / "cache_segmentos.json"
    ruta.write_text(json.dumps({
        "clima": {clave_clima("Oriental", "granos_basicos"): {"respuesta": None}},
        "mercado": {clave_mercado("granos_basicos", "subsistencia"): {"respuesta": {"mensaje_corto": "m"}}},
    }), encoding="utf-8")
    personas = panel_sintetico().query("zona == 'Oriental'")
    llamadas: list[str] = []

    def clima(zona, cultivo):
        llamadas.append(zona)
        return objeto("c nuevo"), {}

    def mercado(cultivo, escala):
        raise AssertionError("Mercado ya estaba en caché")

    cache = completar_cache(personas, ruta, clima, mercado, progreso=lambda _: None)
    assert llamadas == ["Oriental"]
    assert cache["clima"][clave_clima("Oriental", "granos_basicos")]["respuesta"]["mensaje_corto"] == "c nuevo"


def test_cache_detiene_la_corrida_tras_dos_fallos(tmp_path: Path) -> None:
    intentos: list[str] = []

    def clima_roto(zona, cultivo):
        intentos.append(zona)
        return None, {"error": "HTTPStatusError: 404"}

    with pytest.raises(ErrorSegmento, match="falló 2 veces.*404"):
        completar_cache(panel_sintetico(), tmp_path / "c.json", clima_roto,
                        lambda c, e: (objeto("m"), {}), progreso=lambda _: None)
    assert len(intentos) == 2
