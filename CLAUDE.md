# CLAUDE.md — Milpa Viva

## Proyecto
Milpa Viva es un gemelo digital del agricultor salvadoreño: prueba alertas climáticas,
consejos de precios y programas agrícolas con agricultores sintéticos
(nvidia/Nemotron-Personas-El-Salvador) antes de lanzarlos a los reales.
Stack: Python 3.12+, Chroma (RAG), Streamlit (dashboard), agentes con loops simples en
Python, sin frameworks de agentes. Inferencia con Nemotron local (Ollama o LM Studio,
backend Vulkan) mediante cliente OpenAI-compatible; respaldo opcional en
integrate.api.nvidia.com.

## Reglas de autoría y redacción (obligatorias)
1. Ninguna línea de atribución a herramientas: prohibido escribir "Co-Authored-By",
   "Generated with Claude Code", "Claude-Session", emojis de robot o firmas similares en
   commits, PRs, README, documentación, comentarios, docstrings o código.
2. No ejecutar `git commit`, `git push`, `gh pr create` ni equivalentes. Al terminar una
   tarea, proponer el mensaje de commit en texto; lo ejecuta la persona con su identidad.
3. No modificar metadatos de autoría: no cambiar `user.name` ni `user.email`, no usar
   `--author` ni `--date`, no `commit --amend`, `rebase`, `filter-branch` ni
   `filter-repo` para reescribir autores o fechas.
4. No agregar colaboradores al repositorio ni cambiar permisos (`gh api .../collaborators`,
   `gh repo edit`).
5. Redacción neutra en commits, comentarios, docstrings, documentación y README: sin
   primera persona (nada de "hice", "agregué", "I", "we") y sin referencias a quién o qué
   escribió el código.
6. Mensajes de commit en imperativo y en español: "Agrega filtro de ocupación agrícola".
7. Antes de dar una tarea por terminada, ejecutar `python scripts/check_authorship.py` y
   corregir cualquier hallazgo.

## Convenciones de código
- Configuración en `config.yaml` y secretos en `.env` (nunca versionar `.env`).
- Toda salida de un agente es JSON validado con Pydantic (`src/milpa/schemas.py`).
- Las cifras agregadas se calculan con pandas; el LLM nunca calcula porcentajes.
- Semillas fijas (`panel.seed`, seed por `uuid`) para corridas reproducibles.
- Datos del escenario en `data/static/` marcados como "Escenario simulado para demo".
- Funciones pequeñas, type hints, docstrings breves en español.

## Estructura
```
milpa-viva/
├── CLAUDE.md  README.md  config.yaml  requirements.txt  .env.example
├── .claude/settings.json
├── .githooks/commit-msg
├── data/
│   ├── raw/            # parquet del dataset (no versionado)
│   ├── panel/          # panel.parquet
│   ├── static/         # pronóstico, boletín, programa A/B, calendario
│   └── geo/            # slv_departamentos.geojson
├── src/milpa/
│   ├── config.py  llm.py  panel.py  rag.py  schemas.py  simulate.py
│   ├── agents/         # clima.py mercado.py agricultor.py analista.py
│   └── prompts/        # clima.md mercado.md agricultor.md analista.md
├── scripts/            # 01_download … 06_analyze, check_authorship.py
├── results/            # bench.csv, run_A/B.jsonl, summary_*.json, analisis_*.json
├── app/dashboard.py
├── docs/               # decisiones.md, ocupaciones.txt, panel_reporte.md
└── tests/
```

## Comandos
- `python scripts/02_build_panel.py --por-depto 20 --seed 42`
- `python scripts/03_ingest_rag.py`
- `python scripts/04_benchmark.py --n 20 --backend ollama --model 4b`
- `python scripts/05_run.py --version A --resume`
- `python scripts/06_analyze.py`
- `streamlit run app/dashboard.py`
- `pytest -q`
