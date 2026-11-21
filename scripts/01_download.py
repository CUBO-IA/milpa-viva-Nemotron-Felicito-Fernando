"""Descarga el dataset de personas y documenta ocupaciones y columnas clave.

Uso: python scripts/01_download.py [--force]
"""

from __future__ import annotations

import argparse

from milpa.config import load_config
from milpa.panel import descargar_personas, escribir_columnas, escribir_ocupaciones, ruta


def main() -> None:
    """Descarga el parquet si no existe y escribe los listados en docs/."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Vuelve a descargar.")
    args = parser.parse_args()

    cfg = load_config()
    df = descargar_personas(cfg, force=args.force)
    print(f"{len(df)} personas en {ruta(cfg['data']['raw_parquet'])}")
    escribir_ocupaciones(df, ruta("docs/ocupaciones.txt"))
    escribir_columnas(df, ruta("docs/columnas.txt"))
    print("Escritos docs/ocupaciones.txt y docs/columnas.txt")


if __name__ == "__main__":
    main()
