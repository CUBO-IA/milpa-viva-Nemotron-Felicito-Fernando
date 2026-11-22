"""Pruebas del RAG y de los agentes con el LLM simulado."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from milpa.agents import agricultor, analista, clima, mercado
from milpa.config import ROOT
from milpa.plantillas import rellenar
from milpa.rag import (
    cortar_por_encabezado,
    fragmentos_de_archivo,
    leer_front_matter,
    recuperar,
)

DOCS = ROOT / "data" / "static"


def test_front_matter_obligatorio() -> None:
    meta, cuerpo = leer_front_matter("---\ndoc_id: x\ntipo: clima\nzona: Todas\nversion: todas\n---\n# T\nTexto")
    assert meta["doc_id"] == "x"
    assert cuerpo.startswith("# T")


def test_front_matter_faltante_falla() -> None:
    with pytest.raises(ValueError):
        leer_front_matter("---\ndoc_id: x\n---\ncuerpo")


def test_documentos_tienen_front_matter_valido() -> None:
    archivos = sorted(DOCS.glob("*.md"))
    assert len(archivos) == 5
    for archivo in archivos:
        meta, _ = leer_front_matter(archivo.read_text(encoding="utf-8"))
        assert meta["tipo"] in {"clima", "mercado", "programa", "calendario"}


def test_cortar_por_encabezado_respeta_tamano() -> None:
    cuerpo = "# A\n" + "linea\n" * 50 + "\n# B\ncorto"
    fragmentos = cortar_por_encabezado(cuerpo, 120)
    assert len(fragmentos) >= 3
    assert all(len(f) <= 120 or "\n" not in f for f in fragmentos)
    assert fragmentos[-1].startswith("# B")


def test_fragmentos_de_archivo_llevan_metadatos() -> None:
    fragmentos = fragmentos_de_archivo(DOCS / "pronostico_canicula.md", 500)
    assert fragmentos
    assert all(f["meta"]["tipo"] == "clima" for f in fragmentos)


def test_morazan_oriental_recupera_seccion_oriental() -> None:
    """Caso del plan: consulta de Morazán con zona Oriental devuelve el pronóstico Oriental primero."""
    resultados = recuperar("canícula Morazán frijol", tipo="clima", zona="Oriental")
    assert resultados, "La recuperación no devolvió fragmentos."
    primero = resultados[0]
    assert primero["meta"]["doc_id"] == "pronostico_canicula"
    assert "Oriental" in primero["texto"]
    assert all(r["meta"]["zona"] in {"Oriental", "Todas"} for r in resultados)


@pytest.mark.parametrize("version", ["A", "B"])
def test_recuperar_programa_filtra_por_version(version: str) -> None:
    """El filtro por versión devuelve solo el programa de esa versión."""
    resultados = recuperar("seguro de cosecha semilla resistente", tipo="programa", version=version)
    assert resultados, "La recuperación no devolvió fragmentos."
    assert {r["meta"]["doc_id"] for r in resultados} == {f"programa_{version}"}
    assert all(r["meta"]["version"] == version for r in resultados)


class _FalsoCliente:
    def __init__(self, fn: Any) -> None:
        self.chat_json = fn


def test_agente_clima_usa_contexto_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    obj = None
    capturado: dict[str, Any] = {}

    def _fake(system: str, user: str, schema: type, seed: int | None = None, **_: Any) -> tuple[Any, dict[str, Any]]:
        capturado["system"] = system
        return obj, {"seed": seed}

    clima.aconsejar("Morazán", "Oriental", "frijol", "pequeña", seed=1, cliente=_FalsoCliente(_fake))
    assert "{contexto_rag}" not in capturado["system"]
    assert "Oriental" in capturado["system"]


def test_agente_mercado_usa_contexto_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, Any] = {}

    def _fake(system: str, user: str, schema: type, seed: int | None = None, **_: Any) -> tuple[Any, dict[str, Any]]:
        capturado["system"] = system
        return None, {}

    mercado.recomendar("Morazán", "maíz", "mediana", seed=1, cliente=_FalsoCliente(_fake))
    assert "{contexto_rag}" not in capturado["system"]
    assert "{departamento}" not in capturado["system"]


def test_agente_agricultor_fija_temperatura_y_restaura() -> None:
    class _Cliente:
        def __init__(self) -> None:
            self.temperature = 0.3
            self.temp_en_llamada: float | None = None

        def chat_json(self, system: str, user: str, schema: type, seed: int | None = None) -> tuple[Any, dict[str, Any]]:
            self.temp_en_llamada = self.temperature
            return None, {}

    cliente = _Cliente()
    persona = {
        "nombre_display": "Ana", "edad": 40, "sexo": "F", "municipio": "San Francisco Gotera",
        "departamento": "Morazán", "zona": "Oriental", "area": "rural", "ocupacion": "agricultor",
        "cultivo": "frijol", "escala": "pequeña", "escolaridad": "primaria", "tipo_hogar": "familiar",
        "estado_civil": "casada", "persona_resumen": "Resumen breve.",
    }
    agricultor.reaccionar(persona, "clima", "mercado", "A", seed=1, cliente=cliente)  # type: ignore[arg-type]
    assert cliente.temp_en_llamada == agricultor.TEMPERATURA
    assert cliente.temperature == 0.3


def test_agente_analista_recibe_cifras(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, Any] = {}

    def _fake(system: str, user: str, schema: type, seed: int | None = None, **_: Any) -> tuple[Any, dict[str, Any]]:
        capturado["system"] = system
        return None, {}

    analista.analizar("A", {"tasa": 0.5}, ["cita"], "resumen", seed=1, cliente=_FalsoCliente(_fake))
    assert '"tasa": 0.5' in capturado["system"]
    assert "{tabla_agregada}" not in capturado["system"]


def test_leer_programa_rechaza_version_desconocida() -> None:
    with pytest.raises(ValueError):
        agricultor.leer_programa("C")


def test_rellenar_conserva_llaves_del_json() -> None:
    assert rellenar("{a} {\"x\": 1}", {"a": "hola"}) == 'hola {"x": 1}'


def test_simplificar_reemplaza_terminos_tecnicos() -> None:
    texto = "La probabilidad de cobertura exige copago y compra al mayorista."
    assert agricultor.simplificar(texto) == (
        "La posibilidad de protección exige pago inicial y compra al comprador grande."
    )


def test_agente_agricultor_version_b_simplifica_mensajes() -> None:
    capturado: dict[str, str] = {}

    class _Cliente:
        temperature = 0.3

        def chat_json(self, system: str, user: str, schema: type, seed: int | None = None) -> tuple[Any, dict[str, Any]]:
            capturado["system"] = system
            return None, {}

    persona = {
        "nombre_display": "Ana", "edad": 40, "sexo": "F", "municipio": "San Francisco Gotera",
        "departamento": "Morazán", "zona": "Oriental", "area": "rural", "ocupacion": "agricultor",
        "cultivo": "frijol", "escala": "pequeña", "escolaridad": "primaria", "tipo_hogar": "familiar",
        "estado_civil": "casada", "persona_resumen": "Resumen breve.",
    }
    agricultor.reaccionar(
        persona, "Alta probabilidad de canícula", "Cobertura y mayoreo", "B", seed=1,
        cliente=_Cliente(),  # type: ignore[arg-type]
    )
    assert "[Clima] Alta posibilidad de canícula" in capturado["system"]
    assert "[Precios] Cobertura y compra grande" in capturado["system"]
