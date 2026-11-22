"""RAG sobre los documentos estáticos de data/static/ con Chroma persistente.

Cada documento inicia con front-matter YAML (doc_id, tipo, zona, version). El
filtro por metadatos evita que un agente de una zona reciba información de otra.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
import yaml
from sentence_transformers import SentenceTransformer

from milpa.config import ROOT, load_config

PREFIJO_PASAJE = "passage: "
PREFIJO_CONSULTA = "query: "
TODOS = "todas"
ZONAS_TODAS = "Todas"


def leer_front_matter(texto: str) -> tuple[dict[str, str], str]:
    """Separa el front-matter YAML del cuerpo del documento."""
    if not texto.startswith("---"):
        raise ValueError("El documento no inicia con front-matter YAML.")
    partes = texto.split("---", 2)
    if len(partes) < 3:
        raise ValueError("Front-matter YAML sin cierre.")
    meta = yaml.safe_load(partes[1]) or {}
    for clave in ("doc_id", "tipo", "zona", "version"):
        if clave not in meta:
            raise ValueError(f"Falta '{clave}' en el front-matter.")
    return {k: str(v) for k, v in meta.items()}, partes[2].strip()


def cortar_por_encabezado(cuerpo: str, tamano: int) -> list[str]:
    """Corta por encabezados Markdown y limita cada fragmento a ~tamano caracteres."""
    secciones: list[str] = []
    actual: list[str] = []
    for linea in cuerpo.splitlines():
        if linea.startswith("#") and actual:
            secciones.append("\n".join(actual).strip())
            actual = []
        actual.append(linea)
    if actual:
        secciones.append("\n".join(actual).strip())

    fragmentos: list[str] = []
    for sec in secciones:
        if not sec:
            continue
        if len(sec) <= tamano:
            fragmentos.append(sec)
            continue
        bloque = ""
        for parrafo in sec.split("\n"):
            if bloque and len(bloque) + len(parrafo) + 1 > tamano:
                fragmentos.append(bloque.strip())
                bloque = parrafo
            else:
                bloque = f"{bloque}\n{parrafo}" if bloque else parrafo
        if bloque.strip():
            fragmentos.append(bloque.strip())
    return fragmentos


def zona_de_seccion(texto: str) -> str:
    """Zona indicada por el encabezado '## Zona <Nombre>' de un fragmento; 'Todas' si no hay."""
    m = re.search(r"^## Zona (\w+)", texto, flags=re.MULTILINE)
    return m.group(1) if m else ZONAS_TODAS


def fragmentos_de_archivo(path: Path, tamano: int) -> list[dict[str, Any]]:
    """Devuelve los fragmentos de un documento con sus metadatos."""
    meta, cuerpo = leer_front_matter(path.read_text(encoding="utf-8"))
    fragmentos = []
    for i, texto in enumerate(cortar_por_encabezado(cuerpo, tamano)):
        zona = meta["zona"]
        if zona == ZONAS_TODAS:
            zona = zona_de_seccion(texto)
        fragmentos.append(
            {
                "id": f"{meta['doc_id']}#{i}",
                "texto": texto,
                "meta": {
                    "doc_id": meta["doc_id"],
                    "tipo": meta["tipo"],
                    "zona": zona,
                    "version": meta["version"],
                },
            }
        )
    return fragmentos


@lru_cache(maxsize=1)
def _modelo() -> SentenceTransformer:
    """Carga una sola vez el modelo de embeddings en CPU."""
    return SentenceTransformer(load_config()["rag"]["modelo_embeddings"], device="cpu")


def _coleccion(reset: bool = False) -> Any:
    cfg = load_config()["rag"]
    cliente = chromadb.PersistentClient(path=str(ROOT / cfg["dir_chroma"]))
    if reset:
        try:
            cliente.delete_collection(cfg["nombre_coleccion"])
        except Exception:  # noqa: BLE001 - la colección puede no existir aún
            pass
    return cliente.get_or_create_collection(
        name=cfg["nombre_coleccion"], metadata={"hnsw:space": "cosine"}
    )


def ingestar(reset: bool = True) -> int:
    """Indexa data/static/*.md en Chroma y devuelve el número de fragmentos."""
    cfg = load_config()["rag"]
    archivos = sorted((ROOT / cfg["dir_docs"]).glob("*.md"))
    fragmentos: list[dict[str, Any]] = []
    for archivo in archivos:
        fragmentos.extend(fragmentos_de_archivo(archivo, cfg["tamano_fragmento"]))
    if not fragmentos:
        raise RuntimeError(f"No hay documentos .md en {cfg['dir_docs']}.")

    vectores = _modelo().encode(
        [PREFIJO_PASAJE + f["texto"] for f in fragmentos],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    col = _coleccion(reset=reset)
    col.upsert(
        ids=[f["id"] for f in fragmentos],
        documents=[f["texto"] for f in fragmentos],
        metadatas=[f["meta"] for f in fragmentos],
        embeddings=[v.tolist() for v in vectores],
    )
    return len(fragmentos)


def _filtro(tipo: str, zona: str | None, version: str | None) -> dict[str, Any]:
    """Construye el filtro Chroma; 'Todas' y 'todas' aplican a cualquier valor."""
    condiciones: list[dict[str, Any]] = [{"tipo": {"$eq": tipo}}]
    if zona is not None:
        condiciones.append({"zona": {"$in": [zona, ZONAS_TODAS]}})
    if version is not None:
        condiciones.append({"version": {"$in": [version, TODOS]}})
    return condiciones[0] if len(condiciones) == 1 else {"$and": condiciones}


def recuperar(
    consulta: str,
    tipo: str,
    zona: str | None = None,
    version: str | None = None,
    k: int | None = None,
) -> list[dict[str, Any]]:
    """Devuelve los k fragmentos más cercanos filtrados por tipo, zona y versión."""
    cfg = load_config()["rag"]
    vector = _modelo().encode(
        PREFIJO_CONSULTA + consulta, normalize_embeddings=True
    ).tolist()
    res = _coleccion().query(
        query_embeddings=[vector],
        n_results=k or cfg["k"],
        where=_filtro(tipo, zona, version),
    )
    salida: list[dict[str, Any]] = []
    for texto, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True
    ):
        salida.append({"texto": texto, "meta": meta, "distancia": dist})
    return salida
