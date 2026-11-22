"""Agente Agricultor: reacción de un agricultor sintético a los mensajes del programa."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from milpa.config import ROOT, load_config
from milpa.llm import LLM
from milpa.plantillas import rellenar
from milpa.schemas import ReaccionesAgricultor, RespuestaAgricultor, restricciones_de

PROMPT = ROOT / "src" / "milpa" / "prompts" / "agricultor.md"
TEMPERATURA = 0.6
MAX_RESUMEN_PERSONA = 400

# Resumen fijo de cada programa, tomado de data/static/programa_{A,B}.md:
# beneficio, requisitos, documentos, copago, dónde se cobra y quién ayuda.
# Conserva el registro de cada versión (A técnico, B en lenguaje simple).
RESUMEN_PROGRAMA: dict[str, list[str]] = {
    "A": [
        "Beneficio: semilla de frijol y maíz resistente a sequía y seguro de cosecha que "
        "cubre pérdidas por canícula mayores al 40 %, mediante índice paramétrico de precipitación.",
        "Requisitos: inscripción en el registro de productores del MAG y cultivar al menos 0.5 manzanas.",
        "Documentos: DUI, NIT y escritura de la propiedad o contrato de arriendo notariado.",
        "Copago: el productor paga 25 % del costo de la semilla al momento de recibirla.",
        "Cobro del seguro: se tramita y se paga en la oficina central del programa en San "
        "Salvador, dentro de 30 días después de la verificación de pérdida.",
        "Quién ayuda: el programa no ofrece acompañamiento; el productor hace el trámite.",
    ],
    "B": [
        "Qué recibe: la misma semilla resistente a sequía y el mismo seguro; le paga si llueve "
        "muy poco y pierde más del 40 % de la cosecha.",
        "Requisitos: estar en el registro de productores del MAG y cultivar al menos 0.5 manzanas.",
        "Documentos: DUI y constancia de la alcaldía de que trabaja la tierra.",
        "Pago: usted paga 25 % de la semilla, pero en la cosecha; nada al recibirla.",
        "Dónde le pagan: en la agencia o alcaldía más cercana, dentro de 30 días después de que "
        "el técnico confirme la pérdida.",
        "Quién ayuda: un técnico lo visita en su parcela para llenar los papeles; usted solo le avisa.",
    ],
}


def resumen_programa(version: str) -> str:
    """Viñetas fijas del programa A o B para el prompt del Agricultor."""
    if version not in RESUMEN_PROGRAMA:
        raise ValueError(f"Versión de programa desconocida: {version}")
    return "\n".join(f"- {v}" for v in RESUMEN_PROGRAMA[version])


def leer_programa(version: str, carpeta: Path | None = None) -> str:
    """Devuelve el texto del programa A o B desde data/static/."""
    if version not in ("A", "B"):
        raise ValueError(f"Versión de programa desconocida: {version}")
    carpeta = carpeta or ROOT / load_config()["rag"]["dir_docs"]
    return (carpeta / f"programa_{version}.md").read_text(encoding="utf-8")


_REEMPLAZOS_SIMPLES = (
    ("probabilidad", "posibilidad"),
    ("inscripción", "inscribirse"),
    ("cobertura", "protección"),
    ("copago", "pago inicial"),
    ("mayoreo", "compra grande"),
    ("mayorista", "comprador grande"),
)


def simplificar(texto: str) -> str:
    """Reescribe un mensaje en lenguaje simple con reemplazos fijos, sin llamar al LLM."""
    for tecnico, simple in _REEMPLAZOS_SIMPLES:
        texto = texto.replace(tecnico, simple)
    return texto


def recortar(texto: str, max_chars: int) -> str:
    """Corta el texto en palabra completa para que no pase de max_chars."""
    if len(texto) <= max_chars:
        return texto
    return texto[: max_chars - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def armar_system(
    persona: dict[str, Any], mensaje_clima: str, mensaje_mercado: str, version: str,
) -> str:
    """Prompt de sistema del Agricultor para una persona y una versión del programa.

    `persona` contiene los campos del perfil usados en la plantilla de agricultor.md.
    Para la versión B, los mensajes recibidos se reescriben con `simplificar`.
    """
    plantilla = PROMPT.read_text(encoding="utf-8")
    if version == "B":
        mensaje_clima = simplificar(mensaje_clima)
        mensaje_mercado = simplificar(mensaje_mercado)
    valores = {
        **persona,
        "persona_resumen": recortar(str(persona.get("persona_resumen", "")), MAX_RESUMEN_PERSONA),
        "texto_programa": resumen_programa(version),
        "mensaje_clima": mensaje_clima,
        "mensaje_mercado": mensaje_mercado,
    }
    return rellenar(plantilla, valores)


def reaccionar(
    persona: dict[str, Any],
    mensaje_clima: str,
    mensaje_mercado: str,
    version: str,
    seed: int | None = None,
    cliente: LLM | None = None,
) -> tuple[RespuestaAgricultor | None, dict[str, Any]]:
    """Reacción de una persona sintética al programa de la versión dada.

    El LLM juzga cada componente del programa (ReaccionesAgricultor); la
    decisión, la probabilidad y las barreras se calculan en Python con
    `schemas.decidir`, en la misma y única llamada por persona. Antes de decidir,
    cada componente se combina con la restricción por regla del perfil
    (config.yaml: agricultor.restricciones): gana la reacción más severa.
    """
    system = armar_system(persona, mensaje_clima, mensaje_mercado, version)
    user = "Respondé como la persona descrita."
    cliente = cliente or LLM()
    original = cliente.temperature
    cliente.temperature = TEMPERATURA
    try:
        reacciones, metricas = cliente.chat_json(system, user, ReaccionesAgricultor, seed=seed)
    finally:
        cliente.temperature = original
    metricas["version"] = version
    if reacciones is None:
        return None, metricas
    regla = restricciones_de(persona, reglas_de(version))
    return RespuestaAgricultor.desde_reacciones(reacciones, regla), metricas


def reglas_de(version: str) -> dict[str, dict[str, dict[str, str]]]:
    """Restricciones estructurales de una versión desde config.yaml (vacío si no hay)."""
    return (load_config().get("agricultor", {}).get("restricciones", {}) or {}).get(version, {}) or {}
