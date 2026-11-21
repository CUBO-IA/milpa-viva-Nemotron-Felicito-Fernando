"""Agente Agricultor: reacción de un agricultor sintético a los mensajes del programa."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from milpa.config import ROOT, load_config
from milpa.llm import LLM
from milpa.plantillas import rellenar
from milpa.schemas import RespuestaAgricultor

PROMPT = ROOT / "src" / "milpa" / "prompts" / "agricultor.md"
TEMPERATURA = 0.5


def leer_programa(version: str, carpeta: Path | None = None) -> str:
    """Devuelve el texto del programa A o B desde data/static/."""
    if version not in ("A", "B"):
        raise ValueError(f"Versión de programa desconocida: {version}")
    carpeta = carpeta or ROOT / load_config()["rag"]["dir_docs"]
    return (carpeta / f"programa_{version}.md").read_text(encoding="utf-8")


def reaccionar(
    persona: dict[str, Any],
    mensaje_clima: str,
    mensaje_mercado: str,
    version: str,
    seed: int | None = None,
    cliente: LLM | None = None,
) -> tuple[RespuestaAgricultor | None, dict[str, Any]]:
    """Genera la reacción de una persona sintética al programa de la versión dada.

    `persona` contiene los campos del perfil usados en la plantilla de agricultor.md.
    """
    plantilla = PROMPT.read_text(encoding="utf-8")
    valores = {
        **persona,
        "texto_programa": leer_programa(version),
        "mensaje_clima": mensaje_clima,
        "mensaje_mercado": mensaje_mercado,
    }
    system = rellenar(plantilla, valores)
    user = "Respondé como la persona descrita."
    cliente = cliente or LLM()
    original = cliente.temperature
    cliente.temperature = TEMPERATURA
    try:
        obj, metricas = cliente.chat_json(system, user, RespuestaAgricultor, seed=seed)
    finally:
        cliente.temperature = original
    metricas["version"] = version
    return obj, metricas
