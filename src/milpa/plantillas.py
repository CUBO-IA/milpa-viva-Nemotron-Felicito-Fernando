"""Relleno de plantillas de prompt sin interpretar las llaves del JSON de ejemplo.

Los prompts incluyen ejemplos de JSON con llaves literales, por lo que
str.format() no sirve. Solo se reemplazan los marcadores {nombre} conocidos.
"""

from __future__ import annotations

from typing import Any


def rellenar(plantilla: str, valores: dict[str, Any]) -> str:
    """Sustituye cada marcador {clave} por su valor; deja intactas las demás llaves."""
    texto = plantilla
    for clave, valor in valores.items():
        texto = texto.replace("{" + clave + "}", str(valor))
    return texto
