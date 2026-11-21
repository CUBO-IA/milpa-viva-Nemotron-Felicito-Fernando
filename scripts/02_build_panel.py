"""Construye el panel de agricultores sintéticos y su reporte.

Uso: python scripts/02_build_panel.py --por-depto 20 --seed 42
"""

from __future__ import annotations

import argparse

import pandas as pd

from milpa.config import load_config
from milpa.panel import construir_panel, descargar_personas, escribir_reporte, ruta


def main() -> None:
    """Lee el parquet crudo, muestrea el panel y escribe parquet y reporte."""
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--por-depto", type=int, default=cfg["panel"]["por_depto"])
    parser.add_argument("--seed", type=int, default=cfg["panel"]["seed"])
    args = parser.parse_args()

    df = descargar_personas(cfg)
    panel, resultados = construir_panel(df, cfg, args.por_depto, args.seed)

    destino = ruta(cfg["data"]["panel_parquet"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(destino, index=False)
    escribir_reporte(panel, resultados, ruta("docs/panel_reporte.md"), args.por_depto, args.seed)

    faltantes = sum(r.faltantes for r in resultados)
    print(f"Panel: {len(panel)} filas en {destino} (faltantes: {faltantes})")
    print("Reporte: docs/panel_reporte.md")
    with pd.option_context("display.width", 200):
        print(pd.crosstab(panel["department"], panel["cultivo_principal"], margins=True))
        print(panel["escala"].value_counts().to_string())


if __name__ == "__main__":
    main()
