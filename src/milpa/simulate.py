"""Simulación de la población sintética con el programa A o B (plan, sección 5, P5).

Clima se calcula una vez por (zona, cultivo) y Mercado una vez por (cultivo,
escala); ambos se comparten entre las versiones A y B. Cada persona produce una línea en
results/run_{version}.jsonl; las personas ya escritas se omiten al reanudar.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from milpa.config import ROOT
from milpa.panel import historia_corta

MAX_HISTORIA = 400


def ruta_run(version: str, carpeta: Path | None = None) -> Path:
    """Ruta del JSONL de resultados de una versión."""
    return (carpeta or ROOT / "results") / f"run_{version}.jsonl"


def ruta_cache(carpeta: Path | None = None) -> Path:
    """Ruta de la caché de segmentos compartida por A y B."""
    return (carpeta or ROOT / "results") / "cache_segmentos.json"


def leer_jsonl(ruta: Path, tolerante: bool = False) -> list[dict[str, Any]]:
    """Lee un JSONL; devuelve lista vacía si no existe.

    Con `tolerante=True` se omiten las líneas que no son JSON válido, como la
    última de un archivo que otra corrida está escribiendo. Para reanudar
    (`uuids_escritos`) se usa el modo estricto, para no continuar sobre un archivo dañado.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    filas = []
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            try:
                filas.append(json.loads(linea))
            except json.JSONDecodeError:
                if not tolerante:
                    raise
    return filas


def uuids_escritos(ruta: Path) -> set[str]:
    """UUID ya presentes en el JSONL, para no duplicar al reanudar."""
    return {str(r["uuid"]) for r in leer_jsonl(ruta)}


def clave_clima(zona: str, cultivo: str) -> str:
    """Clave del segmento de Clima (zona × cultivo)."""
    return f"{zona}|{cultivo}"


def clave_mercado(cultivo: str, escala: str) -> str:
    """Clave del segmento de Mercado (cultivo × escala)."""
    return f"{cultivo}|{escala}"


def cargar_cache(ruta: Path) -> dict[str, dict[str, Any]]:
    """Carga la caché {"clima": {...}, "mercado": {...}}; vacía si no existe."""
    cache = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    cache.setdefault("clima", {})
    cache.setdefault("mercado", {})
    return cache


def guardar_cache(ruta: Path, cache: dict[str, dict[str, Any]]) -> None:
    """Escribe la caché de segmentos en JSON legible."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def segmentos_unicos(personas: pd.DataFrame) -> dict[str, list[tuple[str, str]]]:
    """Segmentos únicos de Clima (zona, cultivo) y de Mercado (cultivo, escala)."""
    clima = personas[["zona", "cultivo_principal"]].drop_duplicates()
    mercado = personas[["cultivo_principal", "escala"]].drop_duplicates()
    return {
        "clima": sorted(map(tuple, clima.to_numpy().tolist())),
        "mercado": sorted(map(tuple, mercado.to_numpy().tolist())),
    }


def _metricas_planas(m: dict[str, Any]) -> dict[str, Any]:
    """Quita de las métricas los campos que no son serializables en JSON."""
    return {k: v for k, v in m.items() if isinstance(v, (str, int, float, bool, list, type(None)))}


class ErrorSegmento(RuntimeError):
    """Un segmento de Clima o Mercado no produjo respuesta válida tras los reintentos."""


def completar_cache(
    personas: pd.DataFrame,
    ruta: Path,
    clima_fn: Callable[[str, str], tuple[Any, dict[str, Any]]],
    mercado_fn: Callable[[str, str], tuple[Any, dict[str, Any]]],
    intentos: int = 2,
    progreso: Callable[[str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Calcula los segmentos que faltan o quedaron en None y guarda la caché.

    `clima_fn(zona, cultivo)` y `mercado_fn(cultivo, escala)` devuelven
    (objeto o None, métricas). Si un segmento falla `intentos` veces se lanza
    ErrorSegmento: así la corrida no sigue con mensajes vacíos.
    """
    emit = progreso or print
    cache = cargar_cache(ruta)
    agentes = {
        "clima": (clima_fn, clave_clima),
        "mercado": (mercado_fn, clave_mercado),
    }
    pendientes = [
        (tipo, seg)
        for tipo, segs in segmentos_unicos(personas).items()
        for seg in segs
        if (cache[tipo].get(agentes[tipo][1](*seg)) or {}).get("respuesta") is None
    ]
    por_tipo = {t: sum(1 for x, _ in pendientes if x == t) for t in agentes}
    emit(f"Segmentos por calcular: {len(pendientes)} llamadas "
         f"(clima {por_tipo['clima']}, mercado {por_tipo['mercado']})")
    for k, (tipo, seg) in enumerate(pendientes, start=1):
        fn, clave_fn = agentes[tipo]
        clave = clave_fn(*seg)
        for intento in range(1, intentos + 1):
            obj, m = fn(*seg)
            if obj is not None:
                break
            emit(f"  {tipo} {clave}: intento {intento} falló ({m.get('error', '')[:120]})")
        else:
            raise ErrorSegmento(
                f"El segmento de {tipo} '{clave}' falló {intentos} veces; corrida detenida. "
                f"Último error: {m.get('error', 'sin detalle')}"
            )
        cache[tipo][clave] = {"respuesta": obj.model_dump(), "metricas": _metricas_planas(m)}
        guardar_cache(ruta, cache)
        emit(f"  {tipo} {clave} listo; quedan {len(pendientes) - k} llamadas de segmento")
    return cache


def mensajes_de(persona: pd.Series, cache: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Mensajes cortos de Clima y Mercado del segmento de una persona."""
    clima = cache["clima"][clave_clima(persona["zona"], persona["cultivo_principal"])]
    mercado = cache["mercado"][clave_mercado(persona["cultivo_principal"], persona["escala"])]
    return {
        "clima": clima["respuesta"]["mensaje_corto"],
        "mercado": mercado["respuesta"]["mensaje_corto"],
    }


def ejecutar_persona(
    persona: pd.Series,
    version: str,
    cache: dict[str, dict[str, Any]],
    reaccion_fn: Callable[..., tuple[Any, dict[str, Any]]],
    seed: int,
) -> dict[str, Any]:
    """Corre el Agricultor para una persona y devuelve su línea JSONL."""
    mensajes = mensajes_de(persona, cache)
    perfil = {
        "nombre_display": persona["nombre_display"], "edad": persona["age"],
        "sexo": persona["sex"], "municipio": persona["municipality"],
        "departamento": persona["department"], "zona": persona["zona"],
        "area": persona["area"], "ocupacion": persona["occupation"],
        "cultivo": persona["cultivo_principal"], "escala": persona["escala"],
        "escolaridad": persona["education_level"], "nivel_escolar": persona["escolaridad"],
        "tipo_hogar": persona["household_type"],
        "estado_civil": persona["marital_status"],
        "persona_resumen": historia_corta(persona["persona"], persona["professional_persona"], MAX_HISTORIA),
    }
    inicio = time.perf_counter()
    obj, m = reaccion_fn(perfil, mensajes["clima"], mensajes["mercado"], version,
                         seed=seed_persona(persona["uuid"], seed))
    tiempo = round(time.perf_counter() - inicio, 3)
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
    """Toma `por_depto` personas de cada departamento, en orden fijo por seed y round-robin.

    El orden de salida es la persona 1 de cada departamento, luego la 2, etc., para
    que una corrida cortada quede balanceada entre departamentos.
    """
    p = panel if not deptos else panel[panel["department"].isin(deptos)]
    p = p.assign(_o=[seed_persona(u, seed) for u in p["uuid"]]).sort_values(["_o", "uuid"])
    p = p.assign(_rank=p.groupby("department").cumcount())
    elegidas = p[p["_rank"] < por_depto].sort_values(["_rank", "department"])
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
            met = linea["metricas"]
            emit(f"[{version}] {k}/{total} | {met.get('tiempo_s', 0):.1f} s | "
                 f"prompt {met.get('prompt_tokens', 0)} tok | ETA {eta / 60:.1f} min | "
                 f"{linea['uuid'][:8]}")

    return {
        "version": version,
        "ya_existian": len(hechos),
        "nuevas": total,
        "validas": validas,
        "invalidas": invalidas,
        "tiempo_s": round(time.perf_counter() - inicio, 1),
    }
