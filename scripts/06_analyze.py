"""Resumen con pandas y redacción del Analista (plan, sección 5, P6).

Uso:
  python scripts/06_analyze.py              # resume A y B, si existen, y redacta
  python scripts/06_analyze.py --sin-llm    # solo calcula summary_{A|B}.json

Escribe results/summary_{A|B}.json y results/analisis_{A|B|AB}.json.
El LLM nunca calcula porcentajes: solo redacta sobre la tabla ya calculada.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from milpa.agents.analista import analizar
from milpa.analisis import (
    aplanar_run,
    barreras_frecuencia,
    citas_por_departamento,
    componentes_frecuencia,
    delta_por_departamento,
    metricas_por_grupo,
)
from milpa.config import ROOT, load_config
from milpa.llm import LLM
from milpa.simulate import ruta_run

RESULTADOS = ROOT / "results"


def resumen_version(version: str, df) -> dict[str, Any]:
    """Cifras de una versión: globales, por departamento, barreras y citas."""
    validas = df[df["valida"]]
    globales = metricas_por_grupo(validas).iloc[0].to_dict()
    por_depto = metricas_por_grupo(validas, ["department"])
    return {
        "version": version,
        "invalidas": int((~df["valida"]).sum()),
        "global": {k: (v if isinstance(v, str) else float(v)) for k, v in globales.items()},
        "por_departamento": por_depto.to_dict(orient="records"),
        "componentes_global": componentes_frecuencia(validas),
        "barreras_global": barreras_frecuencia(validas),
        "barreras_por_departamento": barreras_frecuencia(validas, "department"),
        "citas_por_departamento": citas_por_departamento(validas, 2),
    }


def verificar_numeros(texto: str, tabla: dict[str, Any]) -> bool:
    """Revisa que cada número del texto exista en la tabla (salvo 1, 2 y 3 de enumeraciones)."""
    conocidos = {f"{float(x):.1f}" for x in _valores(tabla)}
    conocidos |= {str(int(x)) for x in _valores(tabla) if float(x).is_integer()}
    for num in re.findall(r"\d+(?:[.,]\d+)?", texto):
        normal = num.replace(",", ".")
        if "." in normal:
            normal = f"{float(normal):.1f}"
        if normal not in conocidos and normal not in {"1", "2", "3"}:
            return False
    return True


def _valores(obj: Any):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _valores(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _valores(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield obj


def redactar(version: str, tabla: dict[str, Any], seed: int, cliente: LLM) -> dict[str, Any] | None:
    """Pide el análisis; si un número no está en la tabla, reintenta una vez y luego quita la frase."""
    citas = [f"{d}: {c}" for d, cs in tabla["citas_por_departamento"].items() for c in cs]
    resumen_programa = "Programa de escenario simulado para demo."
    tabla_llm = {k: v for k, v in tabla.items() if k != "citas_por_departamento"}
    for _ in range(2):
        obj, _m = analizar(version, tabla_llm, citas, resumen_programa, seed=seed, cliente=cliente)
        if obj is None:
            return None
        texto = json.dumps(obj.model_dump(), ensure_ascii=False)
        if verificar_numeros(texto, tabla_llm):
            return obj.model_dump()
    dump = obj.model_dump()
    frases = dump["resumen_ejecutivo"].split(". ")
    dump["resumen_ejecutivo"] = ". ".join(f for f in frases if verificar_numeros(f, tabla_llm))
    dump["verificacion_numeros"] = "frases_con_cifra_no_verificada_eliminadas"
    return dump


def main() -> None:
    """Calcula los resúmenes disponibles y, salvo --sin-llm, redacta el análisis."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-llm", action="store_true", help="Solo cifras; no llama al modelo.")
    args = parser.parse_args()
    cfg = load_config()
    seed = cfg["panel"]["seed"]
    cliente = LLM(cfg, model="4b") if not args.sin_llm else None

    RESULTADOS.mkdir(parents=True, exist_ok=True)
    resumenes: dict[str, dict[str, Any]] = {}
    tablas = {}
    for version in ["A", "B"]:
        ruta = ruta_run(version)
        if not ruta.exists():
            continue
        df = aplanar_run(ruta)
        tablas[version] = df
        resumen = resumen_version(version, df)
        resumenes[version] = resumen
        (RESULTADOS / f"summary_{version}.json").write_text(
            json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"summary_{version}.json: n={resumen['global']['n']}")

    if not resumenes:
        raise SystemExit("No hay results/run_A.jsonl ni run_B.jsonl. Corre 05_run.py primero.")

    delta = None
    if "A" in tablas and "B" in tablas:
        delta = delta_por_departamento(
            metricas_por_grupo(tablas["A"][tablas["A"]["valida"]], ["department"]),
            metricas_por_grupo(tablas["B"][tablas["B"]["valida"]], ["department"]),
        )
        (RESULTADOS / "summary_AB.json").write_text(
            json.dumps({"delta_por_departamento": delta}, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.sin_llm:
        return
    for version, tabla in resumenes.items():
        analisis = redactar(version, tabla, seed, cliente)
        (RESULTADOS / f"analisis_{version}.json").write_text(
            json.dumps(analisis, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"analisis_{version}.json: {'ok' if analisis else 'sin respuesta válida'}")

    if delta is not None:
        comparado = {"A": resumenes["A"], "B": resumenes["B"], "delta_por_departamento": delta}
        analisis = redactar("AB", comparado, seed, cliente)
        (RESULTADOS / "analisis_AB.json").write_text(
            json.dumps(analisis, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"analisis_AB.json: {'ok' if analisis else 'sin respuesta válida'}")


if __name__ == "__main__":
    main()
