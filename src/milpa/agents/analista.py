"""Agente Analista: redacta conclusiones sobre una tabla de resultados ya calculada."""

from __future__ import annotations

import json
from typing import Any

from milpa.config import ROOT
from milpa.llm import chat_json
from milpa.plantillas import rellenar
from milpa.schemas import RespuestaAnalista

PROMPT = ROOT / "src" / "milpa" / "prompts" / "analista.md"


def analizar(
    version: str,
    tabla_agregada: dict[str, Any],
    citas: list[str],
    resumen_programa: str,
    seed: int | None = None,
) -> tuple[RespuestaAnalista | None, dict[str, Any]]:
    """Redacta el análisis a partir de cifras ya calculadas con pandas."""
    plantilla = PROMPT.read_text(encoding="utf-8")
    system = rellenar(plantilla, {
        "version": version,
        "tabla_agregada": json.dumps(tabla_agregada, ensure_ascii=False),
        "citas": "\n".join(f"- {c}" for c in citas),
        "resumen_programa": resumen_programa,
    })
    user = "Redactá el análisis con las cifras dadas."
    return chat_json(system, user, RespuestaAnalista, seed=seed)
