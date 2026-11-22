"""Esquemas Pydantic de las salidas de los agentes (plan, sección 4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_PALABRAS_VOZ = 60

BARRERAS_VALIDAS = frozenset(
    {
        "costo_inicial",
        "desconfianza_institucion",
        "tramite_complejo",
        "distancia_agencia",
        "lenguaje_dificil",
        "falta_informacion",
        "riesgo_percibido",
        "sin_tierra_propia",
        "acceso_credito",
        "demora_pago_seguro",
        "ninguna",
    }
)


def _contar_palabras(texto: str) -> int:
    return len(texto.split())


class RespuestaClima(BaseModel):
    """Consejo del Agente Clima para un segmento depto × cultivo × escala."""

    departamento: str
    cultivo: str
    nivel_riesgo: Literal["bajo", "medio", "alto"]
    resumen: str = Field(description="Máximo 40 palabras.")
    acciones: list[str] = Field(min_length=1, max_length=3)
    ventana_siembra: str
    mensaje_corto: str = Field(description="Máximo 35 palabras, para SMS.")
    fuentes: list[str] = Field(default_factory=list)

    @field_validator("resumen")
    @classmethod
    def _max_resumen(cls, v: str) -> str:
        if _contar_palabras(v) > 40:
            raise ValueError("resumen supera 40 palabras.")
        return v.strip()

    @field_validator("mensaje_corto")
    @classmethod
    def _max_mensaje(cls, v: str) -> str:
        if _contar_palabras(v) > 35:
            raise ValueError("mensaje_corto supera 35 palabras.")
        return v.strip()


class RespuestaMercado(BaseModel):
    """Recomendación del Agente Mercado para un segmento."""

    producto: str
    tendencia: Literal["sube", "baja", "estable"]
    recomendacion: Literal["vender_ahora", "almacenar", "vender_escalonado", "reservar_consumo"]
    cuando: str
    donde: str
    precio_referencia_usd_qq: float | None = None
    justificacion: str = Field(description="Máximo 40 palabras.")
    mensaje_corto: str = Field(description="Máximo 35 palabras.")
    fuentes: list[str] = Field(default_factory=list)

    @field_validator("justificacion")
    @classmethod
    def _max_justificacion(cls, v: str) -> str:
        if _contar_palabras(v) > 40:
            raise ValueError("justificacion supera 40 palabras.")
        return v.strip()

    @field_validator("mensaje_corto")
    @classmethod
    def _max_mensaje(cls, v: str) -> str:
        if _contar_palabras(v) > 35:
            raise ValueError("mensaje_corto supera 35 palabras.")
        return v.strip()


class RespuestaAgricultor(BaseModel):
    """Reacción de un agricultor sintético a los mensajes del programa."""

    entiende: Literal["si", "parcial", "no"]
    le_conviene: Literal["si", "no", "no_sabe"]
    decision: Literal["adopta", "no_adopta", "lo_pensara"]
    probabilidad_adopcion: int = Field(ge=0, le=100)
    barreras: list[str] = Field(min_length=1, max_length=3)
    motivo_principal: str = Field(description="Máximo 25 palabras.")
    respuesta_en_su_voz: str = Field(description="Máximo 60 palabras, primera persona.")
    pregunta_que_haria: str

    @field_validator("barreras")
    @classmethod
    def _barreras_en_lista(cls, v: list[str]) -> list[str]:
        desconocidas = [b for b in v if b not in BARRERAS_VALIDAS]
        if desconocidas:
            raise ValueError(f"barreras fuera de la lista permitida: {desconocidas}")
        return v

    @field_validator("motivo_principal")
    @classmethod
    def _max_motivo(cls, v: str) -> str:
        if _contar_palabras(v) > 25:
            raise ValueError("motivo_principal supera 25 palabras.")
        return v.strip()

    @field_validator("respuesta_en_su_voz")
    @classmethod
    def _max_voz(cls, v: str) -> str:
        n = _contar_palabras(v)
        if n > 60:
            raise ValueError(f"respuesta_en_su_voz tiene {n} palabras; máximo 60.")
        return v.strip()

    @model_validator(mode="after")
    def _coherencia(self) -> RespuestaAgricultor:
        """Rango de probabilidad según decision; 'ninguna' solo con 'adopta'."""
        p = self.probabilidad_adopcion
        if self.decision == "adopta" and p < 60:
            raise ValueError("decision 'adopta' requiere probabilidad_adopcion >= 60.")
        if self.decision == "no_adopta" and p > 40:
            raise ValueError("decision 'no_adopta' requiere probabilidad_adopcion <= 40.")
        if self.decision == "lo_pensara" and not (30 <= p <= 70):
            raise ValueError("decision 'lo_pensara' requiere probabilidad_adopcion entre 30 y 70.")
        if "ninguna" in self.barreras and self.decision != "adopta":
            raise ValueError("'ninguna' como barrera solo es válida con decision 'adopta'.")
        return self


class RespuestaAnalista(BaseModel):
    """Redacción del Agente Analista sobre una tabla ya calculada por pandas."""

    class DepartamentoCritico(BaseModel):
        departamento: str
        barrera_principal: str
        explicacion: str

    class BarreraTop(BaseModel):
        barrera: str
        por_que_importa: str

    class Recomendacion(BaseModel):
        accion: str
        barrera_que_ataca: str
        departamentos: list[str]

    resumen_ejecutivo: str = Field(description="Máximo 80 palabras.")
    departamentos_criticos: list[DepartamentoCritico]
    barreras_top: list[BarreraTop]
    mensajes_que_funcionaron: list[str]
    recomendaciones: list[Recomendacion]
    comparacion_ab: str | None = None

    @field_validator("resumen_ejecutivo")
    @classmethod
    def _max_resumen(cls, v: str) -> str:
        if _contar_palabras(v) > 80:
            raise ValueError("resumen_ejecutivo supera 80 palabras.")
        return v.strip()
