"""Cliente LLM con salida JSON validada por Pydantic.

Servidor principal: LLM_BASE_URL / LLM_MODEL / LLM_API_KEY. Si apunta a Ollama
local (localhost:11434) se usa la API nativa /api/chat; en otro caso, la ruta
OpenAI-compatible /v1 (LM Studio, API de NVIDIA).
Respaldo opcional (USE_FALLBACK=1): FALLBACK_BASE_URL / FALLBACK_MODEL con
NVIDIA_API_KEY, solo cuando falla la conexión con el servidor local.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
import openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from milpa.config import load_config

T = TypeVar("T", bound=BaseModel)

RX_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_DECODER = json.JSONDecoder()


@dataclass
class Backend:
    """Datos de conexión de un servidor OpenAI-compatible."""

    nombre: str
    base_url: str
    model: str
    api_key: str

    @property
    def es_ollama(self) -> bool:
        """True si el servidor es Ollama local (localhost o 127.0.0.1, puerto 11434)."""
        return bool(re.match(r"^https?://(localhost|127\.0\.0\.1):11434\b", self.base_url))

    @property
    def url_nativa(self) -> str:
        """Endpoint /api/chat de Ollama a partir de la base /v1."""
        raiz = re.sub(r"/v1/?$", "", self.base_url.rstrip("/"))
        return f"{raiz}/api/chat"


class ErrorConexion(Exception):
    """Fallo de conexión o timeout con un servidor (activa el respaldo)."""


@dataclass
class Uso:
    """Tokens consumidos por una llamada."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


# --- Limpieza y extracción ----------------------------------------------------


def quitar_think(texto: str) -> str:
    """Elimina bloques <think>…</think> y restos de un bloque sin abrir."""
    texto = RX_THINK.sub("", texto or "")
    if "</think>" in texto.lower():
        texto = re.split(r"</think>", texto, flags=re.IGNORECASE)[-1]
    return texto.strip()


def extraer_json(texto: str) -> dict[str, Any]:
    """Devuelve el primer objeto JSON del texto; ValueError si no hay ninguno."""
    for i, c in enumerate(texto):
        if c == "{":
            try:
                obj, _ = _DECODER.raw_decode(texto, i)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    raise ValueError("No se encontró un objeto JSON en la respuesta.")


def parsear(texto: str, schema: type[T]) -> T:
    """Limpia, extrae y valida la respuesta contra el esquema."""
    return schema.model_validate(extraer_json(quitar_think(texto)))


def _uso(usage: Any) -> Uso:
    """Convierte el usage de la API OpenAI en Uso."""
    if usage is None:
        return Uso()
    return Uso(usage.prompt_tokens or 0, usage.completion_tokens or 0)


# --- Cliente ------------------------------------------------------------------


class LLM:
    """Cliente con respaldo opcional y degradación de JSON Schema a texto."""

    def __init__(self, cfg: dict[str, Any] | None = None, model: str | None = None):
        self.cfg = cfg or load_config()
        llm = self.cfg["llm"]
        self.temperature = llm["temperature"]
        self.max_tokens = llm["max_tokens"]
        self.timeout = llm["timeout_s"]
        self.num_ctx = llm.get("num_ctx", 4096)
        modelo = llm.get("modelos", {}).get(model, model) if model else llm["model"]
        self.principal = Backend("local", llm["base_url"], modelo, llm["api_key"])
        fb = self.cfg["fallback"]
        self.respaldo = (
            Backend("fallback", fb["base_url"], fb["model"], fb["api_key"])
            if fb.get("enabled") and fb.get("api_key")
            else None
        )
        self._clientes: dict[str, OpenAI] = {}
        self._sin_schema: set[str] = set()
        self._lock = threading.Lock()

    def _cliente(self, b: Backend) -> OpenAI:
        """Cliente OpenAI reutilizable por backend."""
        with self._lock:
            if b.nombre not in self._clientes:
                self._clientes[b.nombre] = OpenAI(
                    base_url=b.base_url, api_key=b.api_key or "none",
                    timeout=self.timeout, max_retries=0,
                )
            return self._clientes[b.nombre]

    def _llamar(
        self, b: Backend, mensajes: list[dict[str, str]], schema: type[BaseModel],
        seed: int | None,
    ) -> tuple[str, Uso, str]:
        """Una llamada; devuelve (texto, uso, modo). ErrorConexion si no hay servidor."""
        if b.es_ollama:
            return self._llamar_ollama(b, mensajes, schema, seed)
        return self._llamar_v1(b, mensajes, schema, seed)

    def _llamar_ollama(
        self, b: Backend, mensajes: list[dict[str, str]], schema: type[BaseModel],
        seed: int | None,
    ) -> tuple[str, Uso, str]:
        """API nativa /api/chat: think=false sí desactiva el razonamiento.

        Por /v1, Ollama ignora think=false y el razonamiento consume max_tokens.
        """
        opciones: dict[str, Any] = {
            "num_predict": self.max_tokens, "temperature": self.temperature,
            "num_ctx": self.num_ctx,
        }
        if seed is not None:
            opciones["seed"] = seed
        cuerpo: dict[str, Any] = {
            "model": b.model, "messages": mensajes, "stream": False, "think": False,
            "options": opciones,
        }
        con_schema = b.nombre not in self._sin_schema
        if con_schema:
            cuerpo["format"] = schema.model_json_schema()
        try:
            r = httpx.post(b.url_nativa, json=cuerpo, timeout=self.timeout)
            if r.status_code == 400 and con_schema:
                with self._lock:
                    self._sin_schema.add(b.nombre)
                cuerpo.pop("format")
                con_schema = False
                r = httpx.post(b.url_nativa, json=cuerpo, timeout=self.timeout)
            r.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise ErrorConexion(f"{type(e).__name__}: {e}") from e
        datos = r.json()
        uso = Uso(datos.get("prompt_eval_count") or 0, datos.get("eval_count") or 0)
        texto = (datos.get("message") or {}).get("content") or ""
        return texto, uso, "json_schema" if con_schema else "texto"

    def _llamar_v1(
        self, b: Backend, mensajes: list[dict[str, str]], schema: type[BaseModel],
        seed: int | None,
    ) -> tuple[str, Uso, str]:
        """Ruta /v1 (API de NVIDIA u otros); cae a texto si rechaza el schema."""
        kwargs: dict[str, Any] = dict(
            model=b.model, messages=mensajes, temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if seed is not None:
            kwargs["seed"] = seed
        cli = self._cliente(b)
        try:
            if b.nombre not in self._sin_schema:
                formato = {
                    "type": "json_schema",
                    "json_schema": {"name": schema.__name__,
                                    "schema": schema.model_json_schema()},
                }
                try:
                    r = cli.chat.completions.create(response_format=formato, **kwargs)
                    return r.choices[0].message.content or "", _uso(r.usage), "json_schema"
                except (openai.BadRequestError, openai.UnprocessableEntityError):
                    with self._lock:
                        self._sin_schema.add(b.nombre)
            r = cli.chat.completions.create(**kwargs)
            return r.choices[0].message.content or "", _uso(r.usage), "texto"
        except openai.APIConnectionError as e:
            raise ErrorConexion(f"{type(e).__name__}: {e}") from e

    def chat_json(
        self, system: str, user: str, schema: type[T], seed: int | None = None
    ) -> tuple[T | None, dict[str, Any]]:
        """Pide una respuesta JSON validada; reintenta una vez con el error.

        Devuelve (objeto o None, métricas). Las métricas incluyen latencia_s,
        prompt_tokens, completion_tokens, reintentos, valido, modo, backend,
        model y error.
        """
        metricas: dict[str, Any] = dict(
            latencia_s=0.0, prompt_tokens=0, completion_tokens=0, reintentos=0,
            valido=False, modo="", backend="", model="", error="",
        )
        mensajes = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        backend = self.principal
        inicio = time.perf_counter()
        for intento in range(2):
            try:
                texto, uso, modo = self._llamar(backend, mensajes, schema, seed)
            except ErrorConexion as e:
                if backend is self.principal and self.respaldo is not None:
                    backend = self.respaldo
                    try:
                        texto, uso, modo = self._llamar(backend, mensajes, schema, seed)
                    except (ErrorConexion, openai.OpenAIError, httpx.HTTPError) as e2:
                        metricas["error"] = f"respaldo: {type(e2).__name__}: {e2}"
                        break
                else:
                    metricas["error"] = str(e)
                    break
            except (openai.OpenAIError, httpx.HTTPError) as e:
                metricas["error"] = f"{type(e).__name__}: {e}"
                break
            metricas.update(modo=modo, backend=backend.nombre, model=backend.model)
            metricas["prompt_tokens"] += uso.prompt_tokens
            metricas["completion_tokens"] += uso.completion_tokens
            try:
                obj = parsear(texto, schema)
                metricas.update(valido=True, error="")
                metricas["latencia_s"] = round(time.perf_counter() - inicio, 3)
                return obj, metricas
            except (ValueError, ValidationError) as e:
                metricas["error"] = f"{type(e).__name__}: {str(e)[:300]}"
                if intento == 0:
                    metricas["reintentos"] = 1
                    mensajes = mensajes + [
                        {"role": "assistant", "content": texto},
                        {"role": "user", "content": (
                            f"La respuesta no fue válida: {str(e)[:500]}\n"
                            "Responde solo con el objeto JSON corregido, sin texto adicional."
                        )},
                    ]
        metricas["latencia_s"] = round(time.perf_counter() - inicio, 3)
        return None, metricas


_POR_DEFECTO: LLM | None = None


def chat_json(
    system: str, user: str, schema: type[T], seed: int | None = None
) -> tuple[T | None, dict[str, Any]]:
    """Atajo con un cliente compartido configurado desde config.yaml y .env."""
    global _POR_DEFECTO
    if _POR_DEFECTO is None:
        _POR_DEFECTO = LLM()
    return _POR_DEFECTO.chat_json(system, user, schema, seed)
