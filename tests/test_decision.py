"""Pruebas de la regla de decisión del Agricultor por componentes (sin LLM)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from milpa.agents import agricultor
from milpa.config import load_config
from milpa.schemas import (
    COMPONENTES,
    ReaccionesAgricultor,
    RespuestaAgricultor,
    combinar,
    decidir,
    restricciones_de,
)


def comps(*valores: str) -> dict[str, str]:
    return dict(zip(COMPONENTES, valores, strict=True))


@pytest.mark.parametrize(("valores", "decision", "probabilidad"), [
    (("acepta",) * 5, "adopta", 75),
    (("acepta", "acepta", "acepta", "duda", "duda"), "adopta", 55),
    (("acepta", "acepta", "duda", "duda", "duda"), "adopta", 45),
    (("acepta", "duda", "duda", "duda", "duda"), "lo_pensara", 35),
    (("acepta", "acepta", "acepta", "acepta", "rechaza"), "lo_pensara", 60),
    (("acepta", "acepta", "acepta", "rechaza", "rechaza"), "no_adopta", 45),
    (("rechaza",) * 5, "no_adopta", 0),
    (("duda",) * 5, "lo_pensara", 25),
])
def test_decidir_aplica_la_regla(valores: tuple[str, ...], decision: str, probabilidad: int) -> None:
    d, p, _ = decidir(comps(*valores))
    assert (d, p) == (decision, probabilidad)


def test_min_acepta_viene_de_config_y_se_puede_pasar() -> None:
    assert load_config()["agricultor"]["min_acepta_adopta"] == 2
    dos_acepta = comps("acepta", "acepta", "duda", "duda", "duda")
    assert decidir(dos_acepta)[0] == "adopta"
    assert decidir(dos_acepta, min_acepta=3)[0] == "lo_pensara"


def test_probabilidad_tiene_tope_95() -> None:
    # Con 5 componentes el máximo natural es 75; el tope protege si se agregan componentes.
    _, p, _ = decidir({f"c{i}": "acepta" for i in range(10)})
    assert p == 95


def test_barreras_rechazadas_primero_y_luego_dudas() -> None:
    _, _, barreras = decidir(comps("duda", "acepta", "rechaza", "duda", "rechaza"))
    assert barreras == ["costo_inicial", "lenguaje_dificil", "riesgo_percibido", "distancia_agencia"]


def test_sin_rechazos_ni_dudas_no_hay_barreras() -> None:
    assert decidir(comps(*("acepta",) * 5))[2] == []


def reacciones(**cambios: Any) -> ReaccionesAgricultor:
    base = {c: "acepta" for c in COMPONENTES} | {
        "entiende": "si", "respuesta_en_su_voz": "Me sirve.", "pregunta_que_haria": "¿Cuándo?",
    }
    return ReaccionesAgricultor(**(base | cambios))


def test_desde_reacciones_arma_el_registro_final() -> None:
    r = RespuestaAgricultor.desde_reacciones(reacciones(copago="rechaza", lugar_de_cobro="rechaza"))
    assert r.decision == "no_adopta"
    assert r.probabilidad_adopcion == 45
    assert r.barreras == ["costo_inicial", "distancia_agencia"]
    assert r.componentes["copago"] == "rechaza"


def test_voz_de_mas_de_40_palabras_se_recorta() -> None:
    r = reacciones(respuesta_en_su_voz="si " * 45)
    assert len(r.respuesta_en_su_voz.split()) == 40


def test_voz_de_mas_de_240_caracteres_es_invalida() -> None:
    with pytest.raises(ValidationError):
        reacciones(respuesta_en_su_voz="x" * 241)


def test_reaccion_fuera_de_la_lista_es_invalida() -> None:
    with pytest.raises(ValidationError):
        reacciones(beneficio="tal_vez")


def test_reaccionar_pide_componentes_y_calcula_la_decision() -> None:
    class _Cliente:
        temperature = 0.3
        schema: type | None = None

        def chat_json(self, system: str, user: str, schema: type, seed: int | None = None):
            self.schema = schema
            return reacciones(lenguaje="duda"), {"valido": True}

    cliente = _Cliente()
    persona = {"nombre_display": "Ana", "edad": 40, "persona_resumen": "Breve."}
    obj, m = agricultor.reaccionar(persona, "c", "m", "B", seed=1, cliente=cliente)  # type: ignore[arg-type]
    assert cliente.schema is ReaccionesAgricultor
    assert obj is not None and obj.decision == "adopta" and obj.probabilidad_adopcion == 65
    assert obj.barreras == ["lenguaje_dificil"]
    assert m["version"] == "B"


def test_prompt_tiene_ejemplos_e_instruccion() -> None:
    texto = agricultor.PROMPT.read_text(encoding="utf-8")
    assert "Juzga cada componente por separado según tu situación real; no rechaces todo por costumbre" in texto
    for c in COMPONENTES:
        assert c in texto
    assert texto.count("Ejemplos") == 1


# --- Restricciones estructurales por regla ---------------------------------

REGLAS = load_config()["agricultor"]["restricciones"]


def perfil(escala: str = "mediano", zona: str = "Central", departamento: str = "San Salvador",
           nivel_escolar: str = "superior") -> dict[str, str]:
    return {"escala": escala, "zona": zona, "departamento": departamento, "nivel_escolar": nivel_escolar}


@pytest.mark.parametrize(("p", "esperado"), [
    (perfil(), {}),
    (perfil(escala="subsistencia"), {"requisitos_documentos": "duda", "copago": "duda"}),
    (perfil(escala="pequeño"), {"requisitos_documentos": "duda", "copago": "duda"}),
    (perfil(zona="Oriental", departamento="Morazán"), {"lugar_de_cobro": "duda"}),
    (perfil(zona="Paracentral", departamento="La Paz"), {"lugar_de_cobro": "duda"}),
    (perfil(zona="Occidental", departamento="Santa Ana"), {"lugar_de_cobro": "duda"}),
    (perfil(departamento="Chalatenango"), {"lugar_de_cobro": "duda"}),
    (perfil(departamento="La Libertad"), {}),
    (perfil(nivel_escolar="basica"), {"lenguaje": "duda"}),
    (perfil(nivel_escolar="media"), {"lenguaje": "duda"}),
])
def test_restricciones_version_a(p: dict[str, str], esperado: dict[str, str]) -> None:
    assert restricciones_de(p, REGLAS["A"]) == esperado


@pytest.mark.parametrize(("escala", "esperado"), [
    ("subsistencia", {"copago": "duda"}), ("pequeño", {}), ("mediano", {}),
])
def test_restricciones_version_b_solo_copago_subsistencia(escala: str, esperado: dict[str, str]) -> None:
    p = perfil(escala=escala, zona="Oriental", departamento="Morazán", nivel_escolar="basica")
    assert restricciones_de(p, REGLAS["B"]) == esperado


def test_restriccion_con_varios_campos_toma_la_peor() -> None:
    reglas = {"lugar_de_cobro": {"zona": {"Central": "duda"}, "departamento": {"X": "rechaza"}}}
    assert restricciones_de({"zona": "Central", "departamento": "X"}, reglas) == {"lugar_de_cobro": "rechaza"}


def test_perfil_sin_campos_no_tiene_restricciones() -> None:
    assert restricciones_de({}, REGLAS["A"]) == {}


@pytest.mark.parametrize(("llm", "regla", "final", "origen"), [
    ("acepta", None, "acepta", "llm"),
    ("acepta", "duda", "duda", "regla"),
    ("acepta", "rechaza", "rechaza", "regla"),
    ("duda", "rechaza", "rechaza", "regla"),
    ("rechaza", "duda", "rechaza", "llm"),
    ("duda", "duda", "duda", "ambos"),
])
def test_combinar_toma_la_peor_y_registra_origen(llm: str, regla: str | None, final: str, origen: str) -> None:
    base = {c: "acepta" for c in COMPONENTES} | {"copago": llm}
    componentes, origenes = combinar(base, {"copago": regla} if regla else {})
    assert componentes["copago"] == final and origenes["copago"] == origen
    assert origenes["beneficio"] == "llm"


@pytest.mark.parametrize(("lenguaje", "entiende"), [("acepta", "si"), ("duda", "parcial"), ("rechaza", "no")])
def test_entiende_se_deriva_de_lenguaje_final(lenguaje: str, entiende: str) -> None:
    r = RespuestaAgricultor.desde_reacciones(reacciones(entiende="no"), {"lenguaje": lenguaje})
    assert r.entiende == entiende
    assert r.entiende_llm == "no"


def test_registro_guarda_llm_regla_y_decision_combinada() -> None:
    r = RespuestaAgricultor.desde_reacciones(
        reacciones(), {"requisitos_documentos": "rechaza", "copago": "rechaza"})
    assert r.componentes_llm == {c: "acepta" for c in COMPONENTES}
    assert r.componentes_regla == {"requisitos_documentos": "rechaza", "copago": "rechaza"}
    assert r.origen["copago"] == "regla" and r.origen["beneficio"] == "llm"
    assert r.decision == "no_adopta"
    assert r.barreras == ["tramite_complejo", "costo_inicial"]


def test_reaccionar_aplica_las_reglas_de_config() -> None:
    class _Cliente:
        temperature = 0.3

        def chat_json(self, system: str, user: str, schema: type, seed: int | None = None):
            return reacciones(), {}

    persona = perfil(escala="subsistencia", zona="Oriental", departamento="Morazán", nivel_escolar="basica")
    persona |= {"nombre_display": "Ana", "persona_resumen": "Breve."}
    a, _ = agricultor.reaccionar(persona, "c", "m", "A", seed=1, cliente=_Cliente())  # type: ignore[arg-type]
    b, _ = agricultor.reaccionar(persona, "c", "m", "B", seed=1, cliente=_Cliente())  # type: ignore[arg-type]
    assert a is not None and b is not None
    # A: los cuatro componentes con regla quedan en duda y solo beneficio en acepta -> lo_pensara.
    assert a.componentes["lugar_de_cobro"] == "duda"
    assert a.decision == "lo_pensara" and a.entiende == "parcial"
    assert b.decision == "adopta" and b.componentes["copago"] == "duda" and b.entiende == "si"


def _techo(version: str, zona: str | None = None) -> float:
    """% que adoptaría si el LLM aceptara todo (solo las reglas limitan)."""
    import pandas as pd

    from milpa.config import ROOT

    panel = pd.read_parquet(ROOT / load_config()["data"]["panel_parquet"])
    if zona:
        panel = panel[panel["zona"] == zona]
    todo = {c: "acepta" for c in COMPONENTES}
    adoptan = 0
    for p in panel.itertuples():
        regla = restricciones_de({"escala": p.escala, "zona": p.zona, "departamento": p.department,
                                  "nivel_escolar": p.escolaridad}, REGLAS[version])
        adoptan += decidir(combinar(todo, regla)[0])[0] == "adopta"
    return 100 * adoptan / len(panel)


def test_techo_de_adopcion_cumple_los_rangos_acordados() -> None:
    """docs/decisiones.md: techo A 35-60 % con Oriental < Central; techo B 85-100 %."""
    assert 35 <= _techo("A") <= 60
    assert 85 <= _techo("B") <= 100
    assert _techo("A", "Oriental") < _techo("A", "Central")
