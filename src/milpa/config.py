"""Carga unificada de configuración: parámetros en config.yaml y secretos en .env."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"

ENV_DEFAULTS: dict[str, str] = {
    "LLM_BASE_URL": "http://localhost:11434/v1",
    "LLM_MODEL": "hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M",
    "LLM_API_KEY": "local",
    "FALLBACK_BASE_URL": "https://integrate.api.nvidia.com/v1",
    "FALLBACK_MODEL": "nvidia/nvidia-nemotron-nano-9b-v2",
    "NVIDIA_API_KEY": "",
    "USE_FALLBACK": "0",
}


def _leer_yaml(path: Path) -> dict[str, Any]:
    """Lee un YAML y devuelve un dict (vacío si el archivo no existe)."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _leer_env(path: Path) -> dict[str, str]:
    """Carga .env en el entorno y devuelve las variables conocidas."""
    load_dotenv(path, override=False)
    return {k: os.getenv(k, v) for k, v in ENV_DEFAULTS.items()}


@lru_cache(maxsize=1)
def load_config(
    config_path: Path = CONFIG_PATH, env_path: Path = ENV_PATH
) -> dict[str, Any]:
    """Une config.yaml y .env en un solo dict.

    Las variables de entorno se agregan en las secciones `llm` (servidor
    principal) y `fallback` (respaldo en integrate.api.nvidia.com).
    """
    cfg = _leer_yaml(config_path)
    env = _leer_env(env_path)
    llm = cfg.setdefault("llm", {})
    llm.update(
        base_url=env["LLM_BASE_URL"],
        model=env["LLM_MODEL"],
        api_key=env["LLM_API_KEY"],
    )
    cfg["fallback"] = {
        "base_url": env["FALLBACK_BASE_URL"],
        "model": env["FALLBACK_MODEL"],
        "api_key": env["NVIDIA_API_KEY"],
        "enabled": env["USE_FALLBACK"].strip() == "1",
    }
    cfg["paths"] = {"root": str(ROOT)}
    return cfg
