"""Agente Clima: traduce el pronóstico recuperado por RAG en consejos por segmento."""

from __future__ import annotations

from typing import Any

from milpa.config import ROOT
from milpa.llm import LLM
from milpa.plantillas import rellenar
from milpa.rag import recuperar
from milpa.schemas import RespuestaClima

PROMPT = ROOT / "src" / "milpa" / "prompts" / "clima.md"


def construir_contexto(fragmentos: list[dict[str, Any]]) -> str:
    """Une los fragmentos recuperados con sus doc_id como fuente."""
    return "\n\n".join(f"[{f['meta']['doc_id']}] {f['texto']}" for f in fragmentos)


def aconsejar(
    departamento: str, zona: str, cultivo: str, escala: str, seed: int | None = None,
    cliente: LLM | None = None,
) -> tuple[RespuestaClima | None, dict[str, Any]]:
    """Genera el consejo climático de un segmento depto × cultivo × escala."""
    consulta = f"canícula pronóstico {cultivo} {departamento}"
    fragmentos = recuperar(consulta, tipo="clima", zona=zona)
    plantilla = PROMPT.read_text(encoding="utf-8")
    system = rellenar(plantilla, {
        "departamento": departamento,
        "zona": zona,
        "cultivo": cultivo,
        "escala": escala,
        "contexto_rag": construir_contexto(fragmentos),
    })
    user = f"Segmento: {departamento}, {cultivo}, escala {escala}."
    cliente = cliente or LLM()
    obj, metricas = cliente.chat_json(system, user, RespuestaClima, seed=seed)
    metricas["fragmentos"] = [f["meta"]["doc_id"] for f in fragmentos]
    return obj, metricas
