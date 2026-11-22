"""Simulación de la población con el programa A o B (plan, sección 5, P5).

Uso:
  python scripts/05_run.py --version A --resume
  python scripts/05_run.py --version B --por-depto 2 --deptos Morazán "La Unión"

Escribe results/cache_segmentos.json (compartida entre A y B) y
results/run_{version}.jsonl. Con --resume, las personas ya presentes se omiten.
"""

from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path

import pandas as pd

from milpa.agents.agricultor import reaccionar
from milpa.agents.clima import aconsejar
from milpa.agents.mercado import recomendar
from milpa.config import ROOT, load_config
from milpa.llm import LLM
from milpa.simulate import (
    ErrorSegmento,
    completar_cache,
    correr_version,
    elegir_por_depto,
    ruta_cache,
    ruta_run,
)


def main() -> None:
    """Corre la versión pedida y reporta el resumen."""
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", choices=["A", "B"], required=True)
    parser.add_argument("--por-depto", type=int, default=None, help="Personas por departamento.")
    parser.add_argument("--deptos", nargs="+", default=None, help="Limita la corrida a estos departamentos.")
    parser.add_argument("--resume", action="store_true", help="Omite personas ya escritas en el JSONL.")
    parser.add_argument("--parallel", type=int, choices=[1, 2], default=1)
    parser.add_argument("--model", default=None, help="Alias (4b, 9b) o nombre del modelo.")
    parser.add_argument("--seed", type=int, default=cfg["panel"]["seed"])
    parser.add_argument("--out", default=None, help="JSONL de salida; por defecto results/run_{version}.jsonl.")
    args = parser.parse_args()

    if not args.resume and args.out is None:
        ruta = ruta_run(args.version)
        if ruta.exists():
            raise SystemExit(f"{ruta.name} ya existe. Usa --resume para continuar o borra el archivo.")

    panel = pd.read_parquet(ROOT / cfg["data"]["panel_parquet"])
    por_depto = args.por_depto or cfg["panel"]["por_depto"]
    personas = elegir_por_depto(panel, por_depto, args.seed, args.deptos)
    print(f"{len(personas)} personas en {personas['department'].nunique()} departamentos "
          f"(versión {args.version}, paralelo={args.parallel})")

    llm = LLM(cfg, model=args.model)
    try:
        cache = completar_cache(
            personas,
            ruta_cache(),
            clima_fn=partial(aconsejar, seed=args.seed, cliente=llm),
            mercado_fn=partial(recomendar, seed=args.seed, cliente=llm),
        )
    except ErrorSegmento as e:
        raise SystemExit(f"ERROR: {e}") from e
    reaccion = partial(reaccionar, cliente=llm)
    ruta = Path(args.out) if args.out else ruta_run(args.version)
    resumen = correr_version(personas, args.version, cache, reaccion, args.seed, ruta, args.parallel)
    print(f"\nResultados en {ruta}")
    for clave, valor in resumen.items():
        print(f"  {clave}: {valor}")
    if resumen["nuevas"]:
        print(f"  segundos_por_persona: {resumen['tiempo_s'] / resumen['nuevas']:.1f}")


if __name__ == "__main__":
    main()
