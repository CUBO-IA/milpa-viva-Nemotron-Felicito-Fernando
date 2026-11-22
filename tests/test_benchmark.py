"""Pruebas del prompt del benchmark sin llamar al LLM."""

from __future__ import annotations

import importlib.util
import re
from types import ModuleType

import pandas as pd
import pytest

from milpa.agents.agricultor import leer_programa
from milpa.config import ROOT, load_config
from milpa.plantillas import rellenar
from milpa.rag import recuperar

RUTA_BENCH = ROOT / "scripts" / "04_benchmark.py"


def _cargar_benchmark() -> ModuleType:
    spec = importlib.util.spec_from_file_location("benchmark_04", RUTA_BENCH)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def bench() -> ModuleType:
    return _cargar_benchmark()


@pytest.fixture(scope="module")
def personas(bench: ModuleType) -> pd.DataFrame:
    cfg = load_config()
    panel = pd.read_parquet(ROOT / cfg["data"]["panel_parquet"])
    return bench.elegir_personas(panel, 5, cfg["bench"]["min_deptos"], cfg["panel"]["seed"])


def test_system_de_no_deja_marcadores(bench: ModuleType, personas: pd.DataFrame) -> None:
    plantilla = bench.PROMPT.read_text(encoding="utf-8")
    for _, fila in personas.iterrows():
        texto = bench.system_de(fila, plantilla)
        assert not re.findall(r"\{[a-z_]+\}", texto)


def test_contexto_del_benchmark_no_esta_vacio(bench: ModuleType, personas: pd.DataFrame) -> None:
    for _, fila in personas.iterrows():
        contexto = bench.contexto_de(fila["cultivo_principal"], fila["department"], fila["zona"])
        assert contexto["mensaje_clima"].strip()
        assert contexto["mensaje_mercado"].strip()
        assert leer_programa(fila["version"]).strip()


def test_recuperar_clima_y_mercado_no_vacios(personas: pd.DataFrame) -> None:
    fila = personas.iloc[0]
    clima = recuperar(f"canícula pronóstico {fila['cultivo_principal']}", tipo="clima", zona=fila["zona"])
    mercado = recuperar(f"precio {fila['cultivo_principal']} venta", tipo="mercado")
    assert clima and mercado


def test_elegir_personas_alterna_a_y_b_por_departamento(bench: ModuleType) -> None:
    cfg = load_config()
    panel = pd.read_parquet(ROOT / cfg["data"]["panel_parquet"])
    muestra = bench.elegir_personas(panel, 20, cfg["bench"]["min_deptos"], cfg["panel"]["seed"])
    versiones = muestra.groupby("department")["version"].agg(set)
    conteo = muestra.groupby("department").size()
    for depto, cuenta in conteo.items():
        if cuenta >= 2:
            assert versiones[depto] == {"A", "B"}, depto
        else:
            assert len(versiones[depto]) == 1, depto
