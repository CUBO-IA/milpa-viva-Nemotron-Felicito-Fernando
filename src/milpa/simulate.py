"""Simulación de la población sintética con el programa A o B (plan, sección 5, P5).

Clima y Mercado se calculan una vez por segmento (departamento, cultivo, escala) y
se comparten entre las versiones A y B. Cada persona produce una línea en
results/run_{version}.jsonl; las personas ya escritas se omiten al reanudar.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from milpa.agents.agricultor import reaccionar
from milpa.agents.clima import aconsejar
from milpa.agents.mercado import recomendar
from milpa.config import ROOT
from milpa.llm import LLM
from milpa.panel import historia_corta

MAX_HISTORIA = 400
CLAVE_SEGMENTO = ["departamento", "cultivo", "escala"]


def ruta_run(version: str, carpeta: Path | None = None) -> Path:
    """Ruta del JSONL de resultados de una versión."""
    return (carpeta or ROOT / "results") / f"run_{version}.jsonl"


def ruta_cache(carpeta: Path | None = None) -> Path:
    """Ruta de la caché de segmentos compartida por A y B."""
    return (carpeta or ROOT / "results") / "cache_segmentos.json"


def leer_jsonl(ruta: Path) -> list[dict[str, Any]]:
    """Lee un JSONL; devuelve lista vacía si no existe."""
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def uuids_escritos(ruta: Path) -> set[str]:
    """UUID ya presentes en el JSONL, para no duplicar al reanudar."""
    return {str(r["uuid"]) for r in leer_jsonl(ruta)}


def clave_segmento(depto: str, cultivo: str, escala: str) -> str:
    """Clave textual estable de un segmento para la caché."""
    return f"{depto}|{cultivo}|{escala}"


def cargar_cache(ruta: Path) -> dict[str, dict[str, Any]]:
    """Carga la caché de segmentos; vacía si no existe."""
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


def guardar_cache(ruta: Path, cache: dict[str, dict[str, Any]]) -> None:
    """Escribe la caché de segmentos en JSON legible."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def segmentos_unicos(personas: pd.DataFrame) -> list[dict[str, str]]:
    """Combinaciones únicas (departamento, cultivo, escala) con su zona."""
    unicos = personas[["department", "cultivo_principal", "escala", "zona"]].drop_duplicates()
    return [
        {"departamento": r.department, "cultivo": r.cultivo_principal,
         "escala": r.escala, "zona": r.zona}
        for r in unicos.itertuples()
    ]


def calcular_segmento(
    seg: dict[str, str],
    clima_fn: Callable[..., Any] = aconsejar,
    mercado_fn: Callable[..., Any] = recomendar,
    seed: int = 42,
    cliente: LLM | None = None,
) -> dict[str, Any]:
    """Calcula Clima y Mercado para un segmento; devuelve dicts serializables."""
    clima, m_clima = clima_fn(seg["departamento"], seg["zona"], seg["cultivo"], seg["escala"], seed, cliente)
    mercado, m_merc = mercado_fn(seg["departamento"], seg["cultivo"], seg["escala"], seed, cliente)
    return {
        "clima": clima.model_dump() if clima else None,
        "mercado": mercado.model_dump() if mercado else None,
        "metricas_clima": _metricas_planas(m_clima),
        "metricas_mercado": _metricas_planas(m_merc),
    }


def _metricas_planas(m: dict[str, Any]) -> dict[str, Any]:
    """Quita de las métricas los campos que no son serializables en JSON."""
    return {k: v for k, v in m.items() if isinstance(v, (str, int, float, bool, list, type(None)))}


def completar_cache(
    personas: pd.DataFrame,
    ruta: Path,
    calcular: Callable[[dict[str, str]], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Calcula solo los segmentos que faltan en la caché y la guarda."""
    cache = cargar_cache(ruta)
    for seg in segmentos_unicos(personas):
        clave = clave_segmento(seg["departamento"], seg["cultivo"], seg["escala"])
        if clave not in cache:
            cache[clave] = calcular(seg)
            guardar_cache(ruta, cache)
    return cache


def ejecutar_persona(
    persona: pd.Series,
    version: str,
    cache: dict[str, dict[str, Any]],
    reaccion_fn: Callable[..., tuple[Any, dict[str, Any]]],
    seed: int,
) -> dict[str, Any]:
    """Corre el Agricultor para una persona y devuelve su línea JSONL."""
    clave = clave_segmento(persona["department"], persona["cultivo_principal"], persona["escala"])
    seg = cache[clave]
    mensaje_clima = seg["clima"]["mensaje_corto"] if seg["clima"] else ""
    mensaje_mercado = seg["mercado"]["mensaje_corto"] if seg["mercado"] else ""
    perfil = {
        "nombre_display": persona["nombre_display"], "edad": persona["age"],
        "sexo": persona["sex"], "municipio": persona["municipality"],
        "departamento": persona["department"], "zona": persona["zona"],
        "area": persona["area"], "ocupacion": persona["occupation"],
        "cultivo": persona["cultivo_principal"], "escala": persona["escala"],
        "escolaridad": persona["education_level"], "tipo_hogar": persona["household_type"],
        "estado_civil": persona["marital_status"],
        "persona_resumen": historia_corta(persona["persona"], persona["professional_persona"], MAX_HISTORIA),
    }
    inicio = time.perf_counter()
    obj, m = reaccion_fn(perfil, mensaje_clima, mensaje_mercado, version,
                         seed=seed_persona(persona["uuid"], seed))
    tiempo = round(time.perf_counter() - inicio, 3)
    mensajes = {"clima": mensaje_clima, "mercado": mensaje_mercado}
    return {
        "uuid": persona["uuid"],
        "version": version,
        "department": persona["department"],
        "cultivo_principal": persona["cultivo_principal"],
        "escala": persona["escala"],
        "mensajes": mensajes,
        "respuesta": obj.model_dump() if obj else "invalido",
        "metricas": _metricas_planas({**m, "tiempo_s": tiempo}),
        "fuente": "api" if m.get("backend") == "fallback" else "local",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def seed_persona(uuid: str, base: int) -> int:
    """Semilla determinista por uuid (misma regla que el benchmark)."""
    return int(hashlib.sha256(f"{base}:{uuid}".encode()).hexdigest()[:8], 16)


def elegir_por_depto(panel: pd.DataFrame, por_depto: int, seed: int, deptos: list[str] | None = None) -> pd.DataFrame:
    """Toma las primeras `por_depto` personas de cada departamento en orden fijo por seed."""
    p = panel if not deptos else panel[panel["department"].isin(deptos)]
    p = p.assign(_o=[seed_persona(u, seed) for u in p["uuid"]]).sort_values(["_o", "uuid"])
    p = p.assign(_rank=p.groupby("department").cumcount())
    elegidas = p[p["_rank"] < por_depto].sort_values(["department", "_rank"])
    return elegidas.drop(columns=["_o", "_rank"]).reset_index(drop=True)


def correr_version(
    personas: pd.DataFrame,
    version: str,
    cache: dict[str, dict[str, Any]],
    reaccion_fn: Callable[..., tuple[Any, dict[str, Any]]],
    seed: int,
    ruta: Path,
    parallel: int = 1,
    progreso: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Corre una versión para las personas pendientes y añade cada línea al JSONL.

    Las líneas se escriben desde el hilo principal en el orden de `personas`, así
    que una interrupción deja un JSONL válido que `--resume` continúa sin duplicar.
    """
    hechos = uuids_escritos(ruta)
    pendientes = [fila for _, fila in personas.iterrows() if str(fila["uuid"]) not in hechos]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    emit = progreso or print
    validas = invalidas = 0
    inicio = time.perf_counter()
    total = len(pendientes)

    def tarea(persona: pd.Series) -> dict[str, Any]:
        return ejecutar_persona(persona, version, cache, reaccion_fn, seed)

    with ruta.open("a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=parallel) as ex:
        for k, linea in enumerate(ex.map(tarea, pendientes), start=1):
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
            f.flush()
            if linea["respuesta"] == "invalido":
                invalidas += 1
            else:
                validas += 1
            transcurrido = time.perf_counter() - inicio
            eta = transcurrido / k * (total - k)
            emit(f"[{version}] {k}/{total} | ETA {eta / 60:.1f} min | {linea['uuid'][:8]}")

    return {
        "version": version,
        "ya_existian": len(hechos),
        "nuevas": total,
        "validas": validas,
        "invalidas": invalidas,
        "tiempo_s": round(time.perf_counter() - inicio, 1),
    }
