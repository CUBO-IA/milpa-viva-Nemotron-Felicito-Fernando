"""Pruebas de la ruta 'Correr en vivo' del dashboard (sin modelo ni servidor LLM)."""

from __future__ import annotations

import importlib.util
import json
import socket
from pathlib import Path

import pandas as pd
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


# --- Resultados parciales ----------------------------------------------------

COMPONENTES_OK = {"beneficio": "acepta", "requisitos_documentos": "acepta", "copago": "duda",
                  "lugar_de_cobro": "acepta", "lenguaje": "acepta"}


def fila(uuid: str, version: str, depto: str, decision: str = "adopta") -> dict:
    return {
        "uuid": uuid, "version": version, "department": depto,
        "mensajes": {"clima": "c", "mercado": "m"},
        "respuesta": {"componentes": COMPONENTES_OK, "origen": {}, "entiende": "si",
                      "decision": decision, "probabilidad_adopcion": 65, "barreras": ["costo_inicial"],
                      "respuesta_en_su_voz": "Me sirve.", "pregunta_que_haria": "¿Cuándo?"},
        "metricas": {"tiempo_s": 14.0, "backend": "local"}, "fuente": "local",
    }


def escribir(ruta: Path, filas: list[dict], cola: str = "") -> None:
    ruta.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas) + cola, encoding="utf-8")


def correr_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str | None = None):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("MILPA_RESULTADOS", str(tmp_path))
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{puerto_cerrado()}/v1")
    at = AppTest.from_file(str(RAIZ / "app" / "dashboard.py"), default_timeout=60)
    at.run()
    if version:
        at.sidebar.selectbox[0].set_value(version).run()
    return at


def test_dashboard_parcial_con_linea_a_medio_escribir_no_se_cae(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    escribir(tmp_path / "run_A.jsonl",
             [fila("a1", "A", "Morazán"), fila("a2", "A", "Santa Ana", "no_adopta")],
             cola='{"uuid": "a3", "versi')  # la corrida está escribiendo esta línea
    at = correr_app(tmp_path, monkeypatch)
    assert not at.exception
    assert any(m.label == "Adopción A" and m.value == "50.0%" for m in at.metric)
    tabla = at.dataframe[0].value
    assert set(tabla["department"]) >= {"Morazán", "Santa Ana", "Cabañas"}  # Cabañas sin filas
    cabanas = tabla[tabla["department"] == "Cabañas"].iloc[0]
    assert cabanas["n_A"] == 0 and pd.isna(cabanas["adopcion_pct_A"])


def test_dashboard_a_vs_b_con_b_sin_archivo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    escribir(tmp_path / "run_A.jsonl", [fila("a1", "A", "Morazán")])
    at = correr_app(tmp_path, monkeypatch, "A vs B")
    assert not at.exception
    etiquetas = {m.label: m.value for m in at.metric}
    assert etiquetas["Adopción A"] == "100.0%" and etiquetas["Adopción B"] == "—"
    assert etiquetas["Delta B−A (adopción)"] == "—"


def test_dashboard_sin_corridas_muestra_aviso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at = correr_app(tmp_path, monkeypatch)
    assert not at.exception
    assert any("Aún no hay filas" in w.value for w in at.warning)


def test_cargar_run_ve_filas_nuevas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dash = cargar_dashboard()
    monkeypatch.setattr(dash, "RESULTADOS", tmp_path)
    ruta = tmp_path / "run_A.jsonl"
    escribir(ruta, [fila("a1", "A", "Morazán")])
    assert len(dash.cargar_run("A")) == 1
    escribir(ruta, [fila("a1", "A", "Morazán"), fila("a2", "A", "La Unión")])
    assert len(dash.cargar_run("A")) == 2


def test_corrida_en_curso_segun_fecha_de_modificacion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import time

    dash = cargar_dashboard()
    monkeypatch.setattr(dash, "RESULTADOS", tmp_path)
    assert dash.corrida_en_curso() is False
    ruta = tmp_path / "run_A.jsonl"
    ruta.write_text("", encoding="utf-8")
    assert dash.corrida_en_curso() is True
    viejo = time.time() - 2 * dash.SEGUNDOS_CORRIDA_ACTIVA
    os.utime(ruta, (viejo, viejo))
    assert dash.corrida_en_curso() is False


def test_tabla_de_departamentos_usa_enteros_para_n(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    escribir(tmp_path / "run_A.jsonl", [fila("a1", "A", "Morazán")])
    at = correr_app(tmp_path, monkeypatch, "A vs B")
    tabla = at.dataframe[0].value
    assert str(tabla["n_A"].dtype) == "Int64" and str(tabla["n_B"].dtype) == "Int64"
