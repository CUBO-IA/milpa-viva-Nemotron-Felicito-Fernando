"""Pruebas de la ruta 'Correr en vivo' del dashboard (sin modelo ni servidor LLM)."""

from __future__ import annotations

import importlib.util
import json
import socket
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def cargar_dashboard():
    """Importa app/dashboard.py como módulo, sin ejecutar la página."""
    spec = importlib.util.spec_from_file_location("dashboard_test", RAIZ / "app" / "dashboard.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def puerto_cerrado() -> int:
    """Puerto local sin ningún servicio escuchando."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_servidor_activo_es_falso_con_puerto_cerrado(monkeypatch: pytest.MonkeyPatch) -> None:
    dash = cargar_dashboard()
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{puerto_cerrado()}/v1")
    assert dash.servidor_activo() is False


def test_lanzar_en_vivo_sin_servidor_devuelve_aviso_en_espanol(monkeypatch: pytest.MonkeyPatch) -> None:
    dash = cargar_dashboard()
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{puerto_cerrado()}/v1")

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "Traceback (most recent call last):\nopenai.APIConnectionError"

    monkeypatch.setattr("subprocess.run", lambda *a, **k: Proc())
    ok, mensaje, ruta = dash.lanzar_en_vivo("A", ["Morazán", "La Unión"])
    assert ok is False
    assert mensaje == dash.AVISO_SIN_SERVIDOR
    assert "Traceback" not in mensaje
    assert ruta.parent == dash.RESULTADOS
    assert ruta.name.startswith("live_A_") and ruta.suffix == ".jsonl"


def test_lanzar_en_vivo_usa_salida_live_y_departamentos_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    dash = cargar_dashboard()
    capturado: dict[str, list[str]] = {}

    class Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        capturado["cmd"] = cmd
        return Proc()

    monkeypatch.setattr("subprocess.run", fake_run)
    ok, _, ruta = dash.lanzar_en_vivo("B", ["Morazán", "La Unión"])
    cmd = capturado["cmd"]
    assert ok is True
    assert cmd[cmd.index("--deptos") + 1:cmd.index("--out")] == ["Morazán", "La Unión"]
    assert cmd[cmd.index("--out") + 1] == str(ruta)
    assert "run_A" not in " ".join(cmd) and "run_B" not in " ".join(cmd)
    assert ruta.name.startswith("live_B_") and ruta.suffix == ".jsonl"


def test_resumen_en_vivo_muestra_segundos_y_backend(tmp_path: Path) -> None:
    dash = cargar_dashboard()
    ruta = tmp_path / "live_A_20260101_000000.jsonl"
    registros = [
        {"uuid": "u1", "department": "Morazán", "version": "A",
         "metricas": {"tiempo_s": 12.5, "backend": "ollama"}},
        {"uuid": "u2", "department": "La Unión", "version": "A",
         "metricas": {"tiempo_s": 9.0, "backend": "fallback"}},
    ]
    ruta.write_text("\n".join(json.dumps(r) for r in registros) + "\n", encoding="utf-8")

    tabla = dash.resumen_en_vivo(ruta)
    assert list(tabla["segundos"]) == [12.5, 9.0]
    assert list(tabla["backend"]) == ["ollama", "fallback"]
    assert list(tabla["departamento"]) == ["Morazán", "La Unión"]


def test_ultimo_en_vivo_ignora_corridas_de_otra_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dash = cargar_dashboard()
    monkeypatch.setattr(dash, "RESULTADOS", tmp_path)
    (tmp_path / "live_A_20260101_000000.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "live_A_20260102_000000.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "live_B_20260103_000000.jsonl").write_text("", encoding="utf-8")
    assert dash.ultimo_en_vivo("A").name == "live_A_20260102_000000.jsonl"
    assert dash.ultimo_en_vivo("C") is None
