"""Agente Mercado: recomienda cuándo y dónde vender según el boletín de precios."""

from __future__ import annotations

from typing import Any

from milpa.config import ROOT
from milpa.llm import LLM
from milpa.plantillas import rellenar
from milpa.rag import recuperar
from milpa.schemas import RespuestaMercado

PROMPT = ROOT / "src" / "milpa" / "prompts" / "mercado.md"


def construir_contexto(fragmentos: list[dict[str, Any]]) -> str:
    """Une los fragmentos recuperados con sus doc_id como fuente."""
    return "\n\n".join(f"[{f['meta']['doc_id']}] {f['texto']}" for f in fragmentos)


def recomendar(
    cultivo: str, escala: str, seed: int | None = None, cliente: LLM | None = None,
) -> tuple[RespuestaMercado | None, dict[str, Any]]:
    """Genera la recomendación de venta de un segmento cultivo × escala."""
    consulta = f"precio {cultivo} venta"
    fragmentos = recuperar(consulta, tipo="mercado")
    plantilla = PROMPT.read_text(encoding="utf-8")
    system = rellenar(plantilla, {
        "cultivo": cultivo,
        "escala": escala,
        "contexto_rag": construir_contexto(fragmentos),
    })
    user = f"Segmento: {cultivo}, escala {escala}."
    cliente = cliente or LLM()
    obj, metricas = cliente.chat_json(system, user, RespuestaMercado, seed=seed)
    metricas["fragmentos"] = [f["meta"]["doc_id"] for f in fragmentos]
    return obj, metricas
