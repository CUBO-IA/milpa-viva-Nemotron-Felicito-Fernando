# Decisiones del proyecto

## Benchmark del LLM

Escenario simulado para demo.

### Modelo y backend

Decisión: el benchmark y la simulación usan el backend `ollama` con el modelo `nemotron-3-nano:4b` (alias `4b`). La elección se basa en la prueba de 20 llamadas descrita más abajo, medida con el GGUF de LM Studio; no hay medición con `nemotron-3-nano:4b`. La mediana de 14.16 s y el p90 de 15.10 s caen en el rango G1 del plan, y el 100 % de las respuestas fue JSON válido al primer intento. El backend `lmstudio` queda como alternativa, sin medir.

- Modelo por defecto: alias `4b` en `config.yaml`, que resuelve a `nemotron-3-nano:4b` en Ollama (`http://127.0.0.1:11434/v1`, definido en `.env`). Antes resolvía al GGUF `hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M` de LM Studio; el cambio evita depender de LM Studio y usa el servidor Ollama instalado localmente.
- Alias alternativo: `9b`, que resuelve a `hf.co/bartowski/nvidia_NVIDIA-Nemotron-Nano-9B-v2-GGUF:Q4_K_M`.
- Backend por defecto: `ollama`. La etiqueta se guarda en `backend_etiqueta` del resultado.
- Parámetros de generación: `temperature` 0.3, `max_tokens` 350, `timeout_s` 120, `num_ctx` 4096.

### Límite de tokens

- `max_tokens` es 350, según la sección 4 del plan.

### Asignación de programa A y B

- Cada persona de la muestra recibe el programa A o B según el departamento al que pertenece.
- Dentro de cada departamento, las versiones se alternan en el orden determinista dado por `seed_de(uuid, seed)`. El punto de inicio de la alternancia depende de `seed_de(departamento, seed)`.
- La semilla es `panel.seed` (42) por defecto.
- Límite: un departamento con una sola persona en la muestra recibe una única versión. La regla de alternancia aplica solo a departamentos con dos o más personas. Esta regla fue confirmada por la persona responsable del proyecto frente al requisito literal de cubrir ambas versiones en cada departamento, que no es posible con una sola persona.
- Con la muestra de 20 personas, 14 departamentos tienen al menos una persona. De ellos, 6 tienen dos personas y reciben A y B; 8 tienen una sola persona y reciben una versión.

### Resultado de la prueba de 20 personas (G1)

- Archivo: `results/bench.csv`, 20 llamadas, 14 departamentos, backend `ollama` (`backend_etiqueta`), modelo registrado en la columna `model`: `hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M`. Sin uuid duplicados.
- Aviso: esa corrida se hizo con el GGUF de LM Studio, no con `nemotron-3-nano:4b` de Ollama. El alias `4b` ahora resuelve a `nemotron-3-nano:4b`, así que la medición no corresponde al modelo que declara la decisión de arriba. Hasta repetir el benchmark con `--model 4b`, los tiempos y la validez de este bloque son del GGUF.
- Mediana por llamada: 14.16 s. p90: 15.10 s (15.095 s sin redondear). Tokens de salida por llamada: 94.4 (6.6 tok/s por llamada).
- JSON válido al primer intento: 100 %. Reintentos: 0. Errores: 0.
- Tiempo estimado para A+B: la proyección del script (`810 × tiempo de pared / 20`) necesita el tiempo de pared total, que no se guarda en el CSV. Con la mediana por llamada, 810 × 14.16 s equivale a 3.19 h; ese es el valor que puede recalcularse desde el archivo.
- Regla G1 del plan (mediana entre 6 y 15 s: 20 personas por departamento, ejecución local): **cumple**. La mediana de 14.16 s está dentro del rango. La tabla G1 original no está en el repositorio; el rango se toma de esta sección.

Pendiente, no medido:

- Ejecuciones con `--parallel 2` y con `--backend lmstudio`.
- Modelo `9b`. No se midió; el 4B cumple el criterio de JSON válido.
- Rúbrica de calidad en español natural (Ing. 2, 10 respuestas, ≥ 3.5/5). No realizada.

## RAG y agentes (P5)

- Base vectorial: Chroma, con la colección del programa cargada por `scripts/03_ingest_rag.py`.
- Cada documento de `data/static/` lleva front-matter con la versión del programa (A o B) y la zona. El RAG filtra por versión para que cada persona vea solo el programa que le corresponde.
- La zona de cada fragmento sale del encabezado `## Zona <Nombre>` (`zona_de_seccion`).
- Agentes con loops simples en Python, sin framework: `clima`, `mercado`, `agricultor` y `analista`. Cada salida es JSON validado con Pydantic (`src/milpa/schemas.py`).
- Versión B del agricultor: `simplificar()` es una tabla de reemplazos determinista. No hace una llamada extra al LLM.
- Los agentes del escenario no se ejecutaron contra el modelo real. Las pruebas cubren el RAG y la lógica sin servidor.

## Simulación (P5)

- `src/milpa/simulate.py` contiene `elegir_por_depto`, `correr_version`, `ejecutar_persona` y `completar_cache`.
- Cada registro del JSONL guarda `mensajes`, `respuesta`, `metricas` (con `tiempo_s` y `backend`), `fuente` y `timestamp`.
- La caché de segmentos (`results/cache_segmentos.json`) la comparten A y B, para no recalcular clima y mercado por cada persona.
- `scripts/05_run.py` escribe en `results/run_{version}.jsonl` por defecto. Con `--out` puede escribir a otra ruta.
- Orden round-robin (`elegir_por_depto`): primero la persona 1 de cada departamento, luego la 2, y así sucesivamente. Si la corrida se corta, queda balanceada entre departamentos. `--deptos` filtra los departamentos antes de ordenar y `--resume` omite los uuid ya escritos.
- Segmentos: Clima se calcula una vez por (zona, cultivo) y Mercado una vez por (cultivo, escala). Las entradas en `None` se recalculan. Si un segmento falla 2 veces, la corrida se detiene con `ErrorSegmento` en vez de seguir con mensajes vacíos.

## Decisión del Agricultor por componentes

Con el esquema anterior (el LLM elegía directamente `decision`), el modelo 4B respondía `no_adopta` en casi todos los casos (18 de 20 en el benchmark y 8 de 8 en la prueba A/B). Ahora el LLM solo juzga cada componente del programa, y la decisión se calcula en Python. Sigue siendo una llamada por persona.

**Salida del LLM** (`ReaccionesAgricultor`): `beneficio`, `requisitos_documentos`, `copago`, `lugar_de_cobro` y `lenguaje`, cada uno con valor `acepta`, `duda` o `rechaza`. Además, `entiende` (`si|parcial|no`), `respuesta_en_su_voz` (máximo 40 palabras) y `pregunta_que_haria`. El JSON Schema limita la voz a 240 caracteres y la pregunta a 100, para que la gramática de Ollama cierre el JSON antes de `max_tokens`. Si la voz pasa de 40 palabras, se recorta en lugar de invalidarse, porque un reintento cuesta una llamada completa.

**Regla** (`schemas.decidir`):

| Condición | `decision` |
|---|---|
| 2 o más `rechaza` | `no_adopta` |
| ningún `rechaza` y al menos 2 `acepta` (`agricultor.min_acepta_adopta` en `config.yaml`) | `adopta` |
| cualquier otro caso | `lo_pensara` |

- `probabilidad_adopcion` = 15 × acepta + 5 × duda, con tope de 95. Por ejemplo, 4 acepta y 1 duda dan 65.
- `barreras` = componentes en `rechaza` (primero) o en `duda`, en este orden y con esta equivalencia:

| Componente | Barrera |
|---|---|
| `beneficio` | `riesgo_percibido` |
| `requisitos_documentos` | `tramite_complejo` |
| `copago` | `costo_inicial` |
| `lugar_de_cobro` | `distancia_agencia` |
| `lenguaje` | `lenguaje_dificil` |

- Si todos los componentes son `acepta`, `barreras` queda vacía (no se escribe `ninguna`).
- El JSONL guarda `RespuestaAgricultor` con `componentes` (combinación final), `componentes_llm`, `componentes_regla`, `origen`, `entiende`, `entiende_llm`, `decision`, `probabilidad_adopcion`, `barreras`, `respuesta_en_su_voz` y `pregunta_que_haria`.
- `analisis.componentes_frecuencia` cuenta acepta, duda y rechaza por componente, y en `por_regla` cuántas reacciones finales vinieron de la regla. `06_analyze.py` lo guarda como `componentes_global` y el dashboard lo grafica.
- El prompt incluye 3 ejemplos cortos de reacción, uno por cada decisión posible, y la instrucción "Juzga cada componente por separado según tu situación real; no rechaces todo por costumbre".

### Restricciones estructurales por regla

El 4B no distinguía los componentes: por ejemplo, `requisitos_documentos` salía `acepta` en 24 de 24 respuestas, aunque A exige escritura notariada. Por eso cada componente se combina con una restricción calculada desde el perfil.

**Componente final = la peor reacción entre el LLM y la regla** (rechaza > duda > acepta). La regla nunca mejora lo que dijo el LLM; solo puede empeorarlo. Las reglas viven en `config.yaml` (`agricultor.restricciones`) y se aplican con `schemas.restricciones_de` y `schemas.combinar`. Si varias reglas aplican al mismo componente, gana la más severa.

Versión A:

| Componente | Motivo | Perfil | Reacción mínima |
|---|---|---|---|
| `requisitos_documentos` | escritura notariada | escala subsistencia o pequeño | `duda` |
| `lugar_de_cobro` | oficina central en San Salvador | zona Oriental, Paracentral u Occidental, o departamento Chalatenango | `duda` |
| `copago` | 25 % al recibir la semilla | escala subsistencia o pequeño | `duda` |
| `lenguaje` | redacción técnica | escolaridad básica o media | `duda` |

Versión B:

| Componente | Motivo | Perfil | Reacción mínima |
|---|---|---|---|
| `copago` | 25 % al cosechar | escala subsistencia | `duda` |

- Los perfiles no listados no tienen restricción: el resto de Central, la escala mediano y la escolaridad superior.
- La escolaridad es el grupo del panel (`escolaridad`: basica, media o superior), que en el perfil se llama `nivel_escolar`.
- `entiende` se deriva del componente final `lenguaje`: acepta → `si`, duda → `parcial`, rechaza → `no`. Lo que dijo el modelo se guarda en `entiende_llm`.
- `origen` vale `llm` si la reacción final es la del modelo, `regla` si la regla la empeoró y `ambos` si coincidían.
- `04_benchmark.py` aplica las mismas reglas.

#### Calibración de la severidad

La primera versión de las reglas usaba `rechaza` para subsistencia (en requisitos y copago) y para escolaridad básica (en lenguaje), con la regla "adopta si hay al menos 3 acepta". Con esa configuración, A quedaba en 0 % en la prueba de 12 personas, y el techo de A sobre las 280 personas era 3.6 %: la regla decidía todo. La severidad se recalibró sin cambiar la lógica.

El techo es el porcentaje que adoptaría si el LLM respondiera `acepta` en todos los componentes, de modo que solo limitan las reglas. Se calcula sin llamar al LLM. Objetivos: techo de A entre 35 % y 55 %, con Oriental claramente por debajo de Central; techo de B entre 85 % y 100 %.

Palancas permitidas:

- en A, subsistencia en requisitos y en copago puede pasar de `rechaza` a `duda`;
- en A, lenguaje con escolaridad básica puede pasar de `rechaza` a `duda`;
- `lugar_de_cobro` para la zona Oriental se mantiene en `rechaza`;
- la regla de adopta puede pasar de 3 a 2 `acepta` como mínimo.

Se probaron las 16 combinaciones y solo una cumple: las tres palancas en `duda` y mínimo de 2 `acepta`.

| Combinación | Techo A | Techo B | A Oriental | A Central |
|---|---|---|---|---|
| Original (todas en `rechaza`, mínimo 3) | 3.6 % | 100 % | 0 % | 10.0 % |
| Las tres palancas en `duda`, mínimo 3 | 7.9 % | 100 % | 0 % | 21.2 % |
| Básica en `rechaza`, resto en `duda`, mínimo 2 | 30.7 % | 100 % | 0 % | 52.5 % |
| **Elegida: las tres en `duda`, mínimo 2** | **40.7 %** | **100 %** | **0 %** | **83.8 %** |

- En la combinación elegida, Occidental queda en 41.7 % y Paracentral en 36.7 %.
- Con `lugar_de_cobro` Oriental en `rechaza`, la zona Oriental tenía techo 0 % en A: la regla limitaba a esas personas a `lo_pensara`.

**Segunda calibración.** `lugar_de_cobro` Oriental pasó de `rechaza` a `duda`, para que el LLM también tenga peso en el oriente. Criterio: dejarlo así si el techo de A se mantiene entre 35 % y 60 % y Oriental queda por debajo de Central; si A pasaba de 60 %, volver a `rechaza` solo para subsistencia en Oriental. No hizo falta.

| Configuración | Techo A | Techo B | Oriental | Paracentral | Occidental | Central |
|---|---|---|---|---|---|---|
| Oriental en `rechaza` | 40.7 % | 100 % | 0 % | 36.7 % | 41.7 % | 83.8 % |
| **Vigente: Oriental en `duda`** | **51.4 %** | **100 %** | **37.5 %** | **36.7 %** | **41.7 %** | **83.8 %** |

- Oriental sigue por debajo de Central, y ahora toda la zona Oriental depende de lo que responda el LLM.
- El techo es solo un límite superior. La adopción real depende de lo que responda el LLM.
- `tests/test_decision.py::test_techo_de_adopcion_cumple_los_rangos_acordados` recalcula el techo sobre el panel y falla si un cambio en `config.yaml` saca a A (35–60 %) o a B (85–100 %) de sus rangos, o si Oriental deja de estar por debajo de Central.

## Análisis (P6)

- Las cifras (adopción, intención, comprensión, barreras y deltas B-A por departamento) se calculan con pandas en `src/milpa/analisis.py`. El LLM no calcula porcentajes.
- El LLM solo redacta la tabla ya calculada, con el esquema `RespuestaAnalista`.
- `scripts/06_analyze.py` calcula siempre los resúmenes (`summary_A.json`, `summary_B.json`, `summary_AB.json`) y, por defecto, llama al Analista para redactar `analisis_A.json`, `analisis_B.json` y `analisis_AB.json`.
- El flag `--sin-llm` (desactivado por defecto) omite la llamada al Analista y solo escribe las cifras.

## Dashboard y corrida en vivo (P7 y P8)

- `app/dashboard.py` lee solo `results/` y `data/`. No llama a internet ni al LLM en modo precalculado.
- El botón "Correr en vivo" lanza `scripts/05_run.py` solo para Morazán y La Unión, con `--out results/live_{version}_{fecha}.jsonl`. La ruta en vivo no lee ni escribe `run_A` ni `run_B`.
- La tabla en vivo muestra por llamada la duración en segundos (`metricas.tiempo_s`) y el backend (`metricas.backend`).
- Si el servidor LLM no responde, la página muestra un aviso en español y no lanza traceback. Esto se prueba con un puerto cerrado.
- La página se comprobó con HTTP 200 sin servidor LLM activo.
- El mapa coroplético usa `data/geo/slv_departamentos.geojson`, con los 14 departamentos. Fuente: geoBoundaries SLV ADM1 (derivada de OpenStreetMap, licencia CC BY-SA 2.0). Cada feature tiene solo `properties.name`, sin el prefijo "Departamento de", y coincide con los nombres del panel.
- Se quitaron intencionalmente los campos `properties.source` y `properties.shapeName` del GeoJSON, porque ningún código, prueba ni documento los usaba. La atribución de la fuente (geoBoundaries SLV ADM1, derivada de OpenStreetMap) y la licencia (CC BY-SA 2.0) se mantienen en esta sección de `docs/decisiones.md`.
- Verificación del mapa: se dibujó con `mapa_adopcion` usando solo valores de adopción de prueba, no resultados reales, en una página temporal dentro de `.freebuff/`, ignorada por git y eliminada después. Se comprobaron 14 polígonos, un color por departamento y ningún error en consola. El dashboard con datos reales (`results/summary_AB.json`) no se ha revisado, porque ese archivo requiere la simulación con el modelo.

## Pendientes abiertos (P5 a P8)

Estado: ninguno de los siguientes elementos se ha ejecutado. No se llamó a LM Studio ni a Ollama en estas etapas.

1. Corrida real con el modelo `4b` y `scripts/05_run.py` contra LM Studio u Ollama (simulación de A y B). Pendiente.
2. Llamada real del Analista (`scripts/06_analyze.py` sin `--sin-llm`). Pendiente.
3. Corrida con el modelo `9b`. Pendiente.
4. Corrida con `--parallel 2`. Pendiente.
5. Rúbrica humana de calidad en español: 10 respuestas, puntaje mínimo 3.5 de 5. Pendiente, requiere revisión de una persona.
6. Corrida en vivo desde el dashboard con servidor activo. Pendiente.
7. Mapa coroplético con datos reales: pendiente. La prueba previa usó valores de prueba, no resultados; falta revisar el dashboard una vez que exista `results/summary_AB.json`.

## Nota de tiempos en la computadora del segundo ingeniero

- El benchmark con `nemotron-3-nano:4b` tarda demasiado en la computadora del segundo ingeniero. Se recomienda reducir la cantidad de llamadas: por ejemplo, `--n 10` en lugar de `--n 20` en `scripts/04_benchmark.py`, y dejar la corrida completa de `05_run.py` para una sola máquina.
- Estado vigente (ver "Corte de sesión" más abajo): la corrida A está detenida, no en curso, con 107 de 280 filas. Se detuvo manualmente porque el proceso demoraba demasiado. El benchmark 4b y la versión B no se han ejecutado. No hay vigilante activo.

## Corte de sesión: corrida A detenida

- Se detuvo de manera manual la corrida A (PID 928607 y su shell 928603) y el watchdog `/tmp/milpa_cadena2.sh` (PID 1039734). Motivo: el proceso demoraba demasiado (unos 70 s por persona). La corrida no está en curso. No se lanzaron el benchmark 4B ni la versión B.
- Estado de A: `results/live_A_20261121_190247.jsonl` con 107 de 280 filas. La última fila puede estar incompleta si el proceso se detuvo a media escritura; `--resume` la reanuda desde la última fila válida.
- Reanudar A: `.venv/bin/python scripts/05_run.py --version A --resume --model 4b --out results/live_A_20261121_190247.jsonl`. Tarda aproximadamente 70 s por persona en la computadora de referencia.
- Siguientes pasos recomendados, en orden:
  1. Reanudar A hasta 280 filas y verificar 14 departamentos.
  2. Ejecutar el benchmark 4B con `--n 10` (no 20) por el tiempo en la computadora del segundo ingeniero.
  3. Ejecutar la versión B con `--resume --model 4b`.
  4. Ejecutar `scripts/06_analyze.py` y revisar `summary_A.json` y `summary_B.json` en el dashboard.
  5. Registrar en este documento los resultados de 4B y B, y la tasa de `invalido` del agricultor.
- Pruebas al cierre: `pytest -q` 34 aprobadas; `check_authorship.py` sin hallazgos.
- Commits: realizados en `ae313e7`, `027082e` y `564ae26`, y enviados a `origin/parte-5-rag-agentes`.

## Estado del código para el siguiente agente

Esta sección y "Corte de sesión" son el estado vigente. Cualquier nota anterior que describa la corrida A como en curso con 103 filas o el watchdog como activo está superada. El watchdog `/tmp/milpa_cadena2.sh` fue detenido y no debe reactivarse.

### Qué está terminado en el código

- Programa A y B: `data/static/programa_A.md` y `programa_B.md`, con front-matter de versión.
- Agricultor: `leer_programa(version)` carga el programa correspondiente. Para B, `reaccionar()` aplica `simplificar()` a los mensajes de clima y mercado antes de la llamada al LLM.
- Simulación: `src/milpa/simulate.py` y `scripts/05_run.py` aceptan `--version A` o `B`, con `--resume`, `--out` y `--deptos`. La salida por defecto es `results/run_{version}.jsonl`.
- Análisis: `scripts/06_analyze.py` genera `summary_A.json`, `summary_B.json`, `summary_AB.json` (delta por departamento), `analisis_A.json`, `analisis_B.json` y `analisis_AB.json`. Con `--sin-llm` omite la redacción.
- Dashboard: `app/dashboard.py` lee los resúmenes y las filas por persona para A y B.
- Pruebas: `pytest -q` pasa 34 pruebas. Compilan `05_run.py`, `06_analyze.py`, `simulate.py`, `agricultor.py` y `dashboard.py`.

### Qué no se ha ejecutado

- Corrida A completa: `results/live_A_20261121_190247.jsonl` tiene 107 de 280 filas. Las filas se escriben una por una; si el proceso se cortó, la última línea puede estar incompleta.
- Benchmark 4B: no se ha ejecutado. Se recomienda `--n 10` por el tiempo en la computadora del segundo ingeniero.
- Versión B completa: no se ha ejecutado. No existe `results/run_B.jsonl` ni `results/live_B_*`.
- Análisis (`06_analyze.py`) sobre corridas completas: no se ha ejecutado.

### Pasos recomendados, en orden

1. Revisar la última línea de `results/live_A_20261121_190247.jsonl`. Si no es JSON válido, borrarla solo en una copia, no en el original.
2. Reanudar A hasta 280 filas: `.venv/bin/python scripts/05_run.py --version A --resume --model 4b --out results/live_A_20261121_190247.jsonl`.
3. Ejecutar el benchmark 4B con `--n 10`: `.venv/bin/python scripts/04_benchmark.py --n 10 --backend ollama --model 4b --parallel 1 --out results/bench.csv`.
4. Ejecutar la versión B: `.venv/bin/python scripts/05_run.py --version B --resume --model 4b`.
5. Ejecutar `.venv/bin/python scripts/06_analyze.py`. Confirmar que `summary_A.json` tiene 14 departamentos y n=280.
6. Revisar el dashboard con `streamlit run app/dashboard.py`.
7. Registrar en este documento la tasa de `invalido` del agricultor por versión y los deltas de `summary_AB.json`.

### Notas

- Los pasos 2 a 4 tardan horas en la computadora de referencia. Ejecutarlos en segundo plano y revisar el log.
- El agricultor tiene una tasa de `invalido` por barreras fuera de la lista permitida, un límite de calidad del modelo y no un defecto de código.
- Commits: el código y la documentación están en la rama `parte-5-rag-agentes` (commits `ae313e7`, `027082e` y `564ae26`).

## Corrida A: no completada, detenida manualmente

- Estado: la corrida A no se completó y no está en curso. Se detuvo de manera manual porque el proceso demoraba demasiado, antes de llegar a las 280 personas de la muestra.
- Archivo: `results/live_A_20261121_190247.jsonl`, con 107 filas válidas (JSON completo, sin líneas inválidas), 107 UUID únicos y 6 departamentos.
- Distribución por departamento en el archivo: Ahuachapán 20, Cabañas 20, Chalatenango 20, Cuscatlán 20, La Libertad 20, La Paz 7. Faltan 8 departamentos (de 14) y 173 personas.
- Log: `results/live_A_20261121_190247.log`, que muestra "280 personas en 14 departamentos (versión A, paralelo=1)" y la carga de pesos, sin error al detener.
- Procesos detenidos: shell PID 928603, proceso Python PID 928607 y watchdog PID 1039734 (`/tmp/milpa_cadena2.sh`). Ninguno sigue activo.
- Efecto: el watchdog no llegó a lanzar el benchmark 4B ni la versión B. Por tanto no existen `results/bench.csv` nuevos, `results/run_B.jsonl` ni `summary_A.json` o `summary_B.json` sobre corridas completas.
- Pendiente para completar A: reanudar con `--resume` sobre el mismo archivo. La corrida es reanudable porque las personas ya escritas se omiten.
- Nota: las filas no incluyen la clave `valida`. La validez de cada respuesta debe calcularse en `06_analyze.py`, no leerse del JSONL en bruto.
- Este documento reemplaza la afirmación anterior de que A seguía en curso.

## Configuración local

- Copiar `.env.example` a `.env` y ajustar los valores. `.env` no se versiona.
- `LLM_BASE_URL` apunta al servidor local (Ollama en `http://localhost:11434/v1` por defecto).
- `NVIDIA_API_KEY` solo se usa si `USE_FALLBACK=1`.
