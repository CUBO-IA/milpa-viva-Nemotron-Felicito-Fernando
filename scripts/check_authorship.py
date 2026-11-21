"""Verifica que los archivos versionados no contengan líneas de atribución a herramientas.

Revisa los archivos rastreados por git más los nuevos no ignorados. Termina con
código 1 si encuentra alguna cadena prohibida por CLAUDE.md.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATRONES: list[re.Pattern[str]] = [
    re.compile(r"co-authored-by", re.IGNORECASE),
    re.compile(r"generated\s+with\s+\[?claude", re.IGNORECASE),
    re.compile(r"claude-session", re.IGNORECASE),
    re.compile("\U0001F916"),
]

EXCLUIDOS = {"CLAUDE.md", ".githooks/commit-msg", "scripts/check_authorship.py"}


def archivos_versionados() -> list[str]:
    """Lista archivos rastreados y nuevos no ignorados según git."""
    salida = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return [line for line in salida.splitlines() if line and line not in EXCLUIDOS]


def revisar(rel: str) -> list[str]:
    """Devuelve los hallazgos de un archivo como 'ruta:línea: texto'."""
    path = ROOT / rel
    try:
        texto = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return []
    hallazgos = []
    for n, linea in enumerate(texto.splitlines(), start=1):
        if any(p.search(linea) for p in PATRONES):
            hallazgos.append(f"{rel}:{n}: {linea.strip()}")
    return hallazgos


def main() -> int:
    """Ejecuta la revisión y devuelve el código de salida."""
    hallazgos = [h for rel in archivos_versionados() for h in revisar(rel)]
    for h in hallazgos:
        print(h, file=sys.stderr)
    if hallazgos:
        print(f"check_authorship: {len(hallazgos)} hallazgo(s).", file=sys.stderr)
        return 1
    print("check_authorship: sin hallazgos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
