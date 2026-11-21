"""Esquemas Pydantic de las salidas de los agentes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_PALABRAS_VOZ = 40


class RespuestaAgricultor(BaseModel):
    """Reacción de un agricultor sintético a un mensaje o programa."""

    entiende: bool = Field(description="Si entiende el mensaje.")
    decision: Literal["adopta", "no_adopta", "lo_pensara"] = Field(
        description="Decisión frente al programa."
    )
    probabilidad_adopcion: float = Field(ge=0, le=1, description="Entre 0 y 1.")
    barreras: list[str] = Field(default_factory=list, max_length=5)
    respuesta_en_su_voz: str = Field(
        description=f"Respuesta en primera persona, máximo {MAX_PALABRAS_VOZ} palabras."
    )

    @field_validator("respuesta_en_su_voz")
    @classmethod
    def _max_palabras(cls, v: str) -> str:
        """Limita la respuesta a MAX_PALABRAS_VOZ palabras."""
        n = len(v.split())
        if n > MAX_PALABRAS_VOZ:
            raise ValueError(f"respuesta_en_su_voz tiene {n} palabras; máximo {MAX_PALABRAS_VOZ}.")
        return v.strip()
