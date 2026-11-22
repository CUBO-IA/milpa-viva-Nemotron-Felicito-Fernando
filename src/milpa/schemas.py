"""Esquemas Pydantic de las salidas de los agentes (plan, sección 4)."""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator

from milpa.config import load_config

MAX_PALABRAS_VOZ = 40
MAX_CARACTERES_VOZ = 240
MAX_CARACTERES_PREGUNTA = 100

# Literal (y no str) para que el JSON Schema lleve un enum: con `format` de Ollama
# la gramática impide barreras fuera de la lista y evita reintentos.
Barrera = Literal[
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
]
BARRERAS_VALIDAS = frozenset(get_args(Barrera))


def _contar_palabras(texto: str) -> int:
    return len(texto.split())


class RespuestaClima(BaseModel):
    """Consejo del Agente Clima para un segmento zona × cultivo."""

    zona: str
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
    """Recomendación del Agente Mercado para un segmento cultivo × escala."""

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


Reaccion = Literal["acepta", "duda", "rechaza"]
Decision = Literal["adopta", "no_adopta", "lo_pensara"]

# Componentes del programa que el Agricultor juzga por separado, en orden de prompt.
COMPONENTES = ("beneficio", "requisitos_documentos", "copago", "lugar_de_cobro", "lenguaje")

# Barrera que se registra cuando un componente queda en "rechaza" o "duda".
BARRERA_POR_COMPONENTE: dict[str, str] = {
    "beneficio": "riesgo_percibido",
    "requisitos_documentos": "tramite_complejo",
    "copago": "costo_inicial",
    "lugar_de_cobro": "distancia_agencia",
    "lenguaje": "lenguaje_dificil",
}

# Severidad para combinar reacciones: gana la peor (rechaza > duda > acepta).
SEVERIDAD = {"acepta": 0, "duda": 1, "rechaza": 2}
ENTIENDE_POR_LENGUAJE = {"acepta": "si", "duda": "parcial", "rechaza": "no"}

PROBABILIDAD_ACEPTA = 15
PROBABILIDAD_DUDA = 5
PROBABILIDAD_TOPE = 95


class ReaccionesAgricultor(BaseModel):
    """Salida del LLM: reacción de la persona a cada componente del programa."""

    beneficio: Reaccion
    requisitos_documentos: Reaccion
    copago: Reaccion
    lugar_de_cobro: Reaccion
    lenguaje: Reaccion
    entiende: Literal["si", "parcial", "no"]
    # max_length entra al JSON Schema: la gramática de Ollama corta el texto y evita
    # respuestas que no cierran el JSON antes de max_tokens.
    respuesta_en_su_voz: str = Field(max_length=MAX_CARACTERES_VOZ,
                                     description="Máximo 40 palabras, primera persona.")
    pregunta_que_haria: str = Field(max_length=MAX_CARACTERES_PREGUNTA)

    @field_validator("respuesta_en_su_voz")
    @classmethod
    def _max_voz(cls, v: str) -> str:
        """Recorta a 40 palabras: un reintento cuesta una llamada completa al LLM."""
        palabras = v.split()
        if len(palabras) > MAX_PALABRAS_VOZ:
            return " ".join(palabras[:MAX_PALABRAS_VOZ]) + "…"
        return v.strip()

    def componentes(self) -> dict[str, str]:
        """Reacción por componente, en el orden de COMPONENTES."""
        return {c: getattr(self, c) for c in COMPONENTES}


def peor(a: str, b: str) -> str:
    """La reacción más severa de las dos (rechaza > duda > acepta)."""
    return a if SEVERIDAD[a] >= SEVERIDAD[b] else b


def restricciones_de(
    perfil: dict[str, object], reglas_version: dict[str, dict[str, dict[str, str]]],
) -> dict[str, str]:
    """Reacción mínima por componente según el perfil (config.yaml: agricultor.restricciones).

    `reglas_version` es componente -> campo del perfil -> valor -> reacción. Si
    varios campos aplican al mismo componente, gana la reacción más severa. Los
    componentes sin regla que aplique no aparecen en el resultado.
    """
    salida: dict[str, str] = {}
    for componente, por_campo in (reglas_version or {}).items():
        for campo, por_valor in por_campo.items():
            reaccion = (por_valor or {}).get(str(perfil.get(campo)))
            if reaccion is not None:
                salida[componente] = peor(salida.get(componente, "acepta"), reaccion)
    return salida


def combinar(
    llm: dict[str, str], regla: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Componente final = la peor reacción entre LLM y regla, y su origen.

    origen: "llm" si la reacción final vino del LLM (o no había regla), "regla"
    si la regla la empeoró, "ambos" si coincidían.
    """
    final: dict[str, str] = {}
    origen: dict[str, str] = {}
    for c in COMPONENTES:
        r_llm, r_regla = llm[c], regla.get(c)
        if r_regla is None or SEVERIDAD[r_llm] > SEVERIDAD[r_regla]:
            final[c], origen[c] = r_llm, "llm"
        elif SEVERIDAD[r_regla] > SEVERIDAD[r_llm]:
            final[c], origen[c] = r_regla, "regla"
        else:
            final[c], origen[c] = r_llm, "ambos"
    return final, origen


def min_acepta_adopta() -> int:
    """Mínimo de "acepta" para adoptar (config.yaml: agricultor.min_acepta_adopta)."""
    return int(load_config()["agricultor"]["min_acepta_adopta"])


def decidir(
    componentes: dict[str, str], min_acepta: int | None = None,
) -> tuple[str, int, list[str]]:
    """Regla fija (docs/decisiones.md): decision, probabilidad y barreras.

    - no_adopta si hay 2 o más "rechaza";
    - adopta si no hay "rechaza" y hay al menos `min_acepta` "acepta"
      (por defecto, agricultor.min_acepta_adopta de config.yaml);
    - lo_pensara en otro caso.
    probabilidad = 15 por "acepta" + 5 por "duda", con tope 95. Las barreras
    salen de los componentes rechazados (primero) y en duda.
    """
    valores = list(componentes.values())
    acepta, duda, rechaza = (valores.count(x) for x in ("acepta", "duda", "rechaza"))
    if rechaza >= 2:
        decision = "no_adopta"
    elif rechaza == 0 and acepta >= (min_acepta if min_acepta is not None else min_acepta_adopta()):
        decision = "adopta"
    else:
        decision = "lo_pensara"
    probabilidad = min(PROBABILIDAD_ACEPTA * acepta + PROBABILIDAD_DUDA * duda, PROBABILIDAD_TOPE)
    barreras = [BARRERA_POR_COMPONENTE[c] for r in ("rechaza", "duda")
                for c in COMPONENTES if componentes.get(c) == r]
    return decision, probabilidad, barreras


class RespuestaAgricultor(BaseModel):
    """Registro final del Agricultor: reacciones del LLM, restricciones por regla y decisión.

    `componentes` es la combinación final; `componentes_llm` y `componentes_regla`
    guardan cada fuente y `origen` dice de dónde salió cada componente final.
    `entiende` se deriva del componente final `lenguaje`; `entiende_llm` es lo que
    dijo el modelo.
    """

    componentes: dict[str, Reaccion]
    componentes_llm: dict[str, Reaccion] = Field(default_factory=dict)
    componentes_regla: dict[str, Reaccion] = Field(default_factory=dict)
    origen: dict[str, Literal["llm", "regla", "ambos"]] = Field(default_factory=dict)
    entiende: Literal["si", "parcial", "no"]
    entiende_llm: Literal["si", "parcial", "no"] | None = None
    decision: Decision
    probabilidad_adopcion: int = Field(ge=0, le=100)
    barreras: list[Barrera] = Field(default_factory=list, max_length=len(COMPONENTES))
    respuesta_en_su_voz: str
    pregunta_que_haria: str

    @classmethod
    def desde_reacciones(
        cls, r: ReaccionesAgricultor, regla: dict[str, str] | None = None,
    ) -> RespuestaAgricultor:
        """Combina las reacciones del LLM con las restricciones y aplica `decidir`."""
        regla = regla or {}
        componentes, origen = combinar(r.componentes(), regla)
        decision, probabilidad, barreras = decidir(componentes)
        return cls(
            componentes=componentes, componentes_llm=r.componentes(), componentes_regla=regla,
            origen=origen, entiende=ENTIENDE_POR_LENGUAJE[componentes["lenguaje"]],
            entiende_llm=r.entiende, decision=decision,
            probabilidad_adopcion=probabilidad, barreras=barreras,
            respuesta_en_su_voz=r.respuesta_en_su_voz, pregunta_que_haria=r.pregunta_que_haria,
        )


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
