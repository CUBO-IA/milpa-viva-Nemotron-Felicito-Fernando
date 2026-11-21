"""Benchmark del LLM local con el prompt provisional de agricultor.

Uso: python scripts/04_benchmark.py --n 20 --parallel 1 [--model 4b]
"""

from __future__ import annotations

import argparse
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from milpa.config import ROOT, load_config
from milpa.llm import LLM
from milpa.panel import historia_corta
from milpa.schemas import RespuestaAgricultor

PROMPT = ROOT / "src" / "milpa" / "prompts" / "agricultor.md"
MAX_HISTORIA = 400


def seed_de(uuid: str, base: int) -> int:
    """Semilla determinista por uuid."""
    return int(hashlib.sha256(f"{base}:{uuid}".encode()).hexdigest()[:8], 16)


def elegir_personas(panel: pd.DataFrame, n: int, min_deptos: int, seed: int) -> pd.DataFrame:
    """Toma n personas rotando entre departamentos (orden fijo por seed)."""
    p = panel.assign(_o=[seed_de(u, seed) for u in panel["uuid"]]).sort_values(["_o", "uuid"])
    p["_rank"] = p.groupby("department").cumcount()
    elegidas = p.sort_values(["_rank", "_o"]).head(n).drop(columns=["_o", "_rank"])
    if elegidas["department"].nunique() < min(min_deptos, n):
        raise RuntimeError("No se alcanzó el mínimo de departamentos.")
    return elegidas


def system_de(fila: pd.Series, plantilla: str) -> str:
    """Rellena el prompt de agricultor con los datos de la persona."""
    return plantilla.format(
        nombre=fila["nombre_display"], edad=fila["age"], municipio=fila["municipality"],
        departamento=fila["department"], zona=fila["zona"], area=fila["area"],
        cultivo=fila["cultivo_principal"], escala=fila["escala"],
        escolaridad=fila["education_level"],
        historia=historia_corta(fila["persona"], fila["professional_persona"], MAX_HISTORIA),
    )


def correr_una(llm: LLM, fila: pd.Series, plantilla: str, mensaje: str, seed: int) -> dict[str, Any]:
    """Ejecuta una llamada y arma la fila de resultados."""
    obj, m = llm.chat_json(system_de(fila, plantilla), mensaje, RespuestaAgricultor,
                           seed=seed_de(fila["uuid"], seed))
    return {
        "uuid": fila["uuid"], "department": fila["department"],
        "cultivo_principal": fila["cultivo_principal"], "escala": fila["escala"], **m,
        "decision": obj.decision if obj else "",
        "probabilidad_adopcion": obj.probabilidad_adopcion if obj else None,
        "respuesta_en_su_voz": obj.respuesta_en_su_voz if obj else "",
    }


def resumen(df: pd.DataFrame, pared_s: float, parallel: int, llamadas: int) -> pd.DataFrame:
    """Tabla de métricas agregadas calculadas con pandas."""
    lat = df["latencia_s"]
    tok = df["completion_tokens"].sum()
    por_llamada = pared_s / len(df)
    filas = {
        "llamadas": len(df),
        "paralelo": parallel,
        "latencia mediana (s)": round(lat.median(), 2),
        "latencia p90 (s)": round(lat.quantile(0.9), 2),
        "tokens salida / llamada": round(df["completion_tokens"].mean(), 1),
        "tokens/s por llamada": round(tok / lat.sum(), 1) if lat.sum() else 0,
        "tokens/s agregado": round(tok / pared_s, 1) if pared_s else 0,
        "% JSON válido": round(100 * df["valido"].mean(), 1),
        "% con reintento": round(100 * df["reintentos"].gt(0).mean(), 1),
        "s de pared / llamada": round(por_llamada, 2),
        f"proyección {llamadas} llamadas (h)": round(llamadas * por_llamada / 3600, 2),
    }
    return pd.DataFrame({"métrica": filas.keys(), "valor": filas.values()})


def main() -> None:
    """Corre el benchmark, guarda results/bench.csv e imprime el resumen."""
    cfg = load_config()
    b = cfg["bench"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=b["n"])
    parser.add_argument("--parallel", type=int, choices=[1, 2], default=1)
    parser.add_argument("--backend", default="ollama", help="Etiqueta del backend.")
    parser.add_argument("--model", default=None, help="Alias (4b, 9b) o nombre del modelo.")
    parser.add_argument("--seed", type=int, default=cfg["panel"]["seed"])
    parser.add_argument("--out", default="results/bench.csv")
    args = parser.parse_args()

    panel = pd.read_parquet(ROOT / cfg["data"]["panel_parquet"])
    personas = elegir_personas(panel, args.n, b["min_deptos"], args.seed)
    plantilla = PROMPT.read_text(encoding="utf-8")
    llm = LLM(cfg, model=args.model)
    print(f"Modelo: {llm.principal.model} | {args.n} personas de "
          f"{personas['department'].nunique()} deptos | paralelo={args.parallel}")

    _, calentamiento = llm.chat_json(system_de(personas.iloc[0], plantilla), b["mensaje"],
                                     RespuestaAgricultor, seed=0)
    print(f"Calentamiento descartado: {calentamiento['latencia_s']} s "
          f"({calentamiento['error'] or 'ok'})")

    filas = [f for _, f in personas.iterrows()]
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        resultados = list(ex.map(lambda f: correr_una(llm, f, plantilla, b["mensaje"], args.seed), filas))
    pared = time.perf_counter() - inicio

    df = pd.DataFrame(resultados).assign(backend_etiqueta=args.backend, parallel=args.parallel)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")

    errores = df.loc[df["error"].ne(""), "error"].value_counts()
    if not errores.empty:
        print("Errores:\n" + errores.head(5).to_string())
    print(f"\nResultados en {Path(args.out)}\n")
    print(resumen(df, pared, args.parallel, b["llamadas_proyeccion"]).to_string(index=False))


if __name__ == "__main__":
    main()
