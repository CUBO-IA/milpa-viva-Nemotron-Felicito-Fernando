"""Indexa los documentos de data/static/ en la colección Chroma del RAG.

Uso: python scripts/03_ingest_rag.py
"""

from __future__ import annotations

from milpa.rag import ingestar


def main() -> None:
    """Reconstruye la colección y muestra cuántos fragmentos se indexaron."""
    total = ingestar(reset=True)
    print(f"Fragmentos indexados: {total}")


if __name__ == "__main__":
    main()
