# Decisiones del proyecto

## Benchmark del LLM

Escenario simulado para demo.

### Modelo y backend

Decisión: el benchmark y la simulación usan el backend `ollama` con el modelo `hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M` (alias `4b`). La prueba de 20 llamadas descrita más abajo registró ese mismo modelo. La mediana de 14.16 s y el p90 de 15.10 s caen en el rango G1 del plan, y el 100 % de las respuestas fue JSON válido al primer intento. El backend `lmstudio` queda como alternativa, sin medir.

- Modelo por defecto: `LLM_MODEL` en `.env` y alias `4b` en `config.yaml`, ambos `hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M` en Ollama (`http://localhost:11434/v1`). Un alias anterior, `nemotron-3-nano:4b`, no existía en Ollama (respondía 404) y se revirtió.
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
- Esa prueba usó el prompt anterior del Agricultor, en el que el LLM elegía directamente `decision`. Con el prompt por componentes vigente, las pruebas de 12 personas midieron entre 14 y 15 s por persona, sin respuestas inválidas.
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
- Los agentes se ejecutaron contra el modelo real en las corridas de `results/run_A.jsonl` y `run_B.jsonl`. Las pruebas automáticas (`pytest`) cubren el RAG y la lógica sin servidor.

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

- `app/dashboard.py` lee solo `results/` y `data/`, sin internet ni LLM. Calcula adopción, intención, componentes y barreras en cada recarga directamente desde `results/run_A.jsonl` y `run_B.jsonl`, así que funciona con corridas parciales o en curso: muestra el avance (n de 280 por versión), n por departamento y versión (los departamentos sin filas salen con n = 0), tolera una última línea a medio escribir y relee el archivo cuando cambia. Los `analisis_*.json` del Analista son opcionales. Mientras algún `run_*.jsonl` haya cambiado en los últimos 5 minutos, el botón "Correr en vivo" se desactiva.
- El botón "Correr en vivo" lanza `scripts/05_run.py` solo para Morazán y La Unión, con `--out results/live_{version}_{fecha}.jsonl`. La ruta en vivo no lee ni escribe `run_A` ni `run_B`.
- La tabla en vivo muestra por llamada la duración en segundos (`metricas.tiempo_s`) y el backend (`metricas.backend`).
- Si el servidor LLM no responde, la página muestra un aviso en español y no lanza traceback. Esto se prueba con un puerto cerrado.
- La página se comprobó con HTTP 200 sin servidor LLM activo.
- El mapa coroplético usa `data/geo/slv_departamentos.geojson`: geoBoundaries SLV ADM1, versión simplificada (`geoBoundaries-SLV-ADM1_simplified.geojson`), derivada de OpenStreetMap, con licencia CC BY-SA 2.0. Tiene 14 features y el nombre está en `properties.shapeName`; doce traen el prefijo "Departamento de" y dos no (La Libertad y San Vicente).
- Unión con el panel: `sin_tildes` normaliza el nombre (sin tildes, en minúsculas y sin el prefijo "Departamento de"), y los 14 departamentos coinciden. `CORRECCIONES_GEO` queda vacío, disponible para nombres que no coincidan. Si algún departamento queda sin polígono, se imprime en consola y la página muestra un aviso. Se dibuja con `px.choropleth_map`, estilo `white-bg` (sin teselas externas), centrado en lat 13.75, lon −88.9, zoom 7, con la misma escala 0–100 para A y B.
- Verificación: con `AppTest`, sobre los resultados reales de `run_A.jsonl` y `run_B.jsonl`, las vistas A y "A vs B" cargan sin excepción y cada mapa pinta los 14 polígonos con la escala 0–100. `tests/test_dashboard.py` ejecuta la página completa sobre carpetas temporales: corrida parcial con una línea cortada, B sin archivo, sin corridas, relectura de filas nuevas y botón en vivo bloqueado.

## Estado y pendientes

- Corridas: `results/run_A.jsonl` y `run_B.jsonl` se generan con `scripts/05_run.py --version A|B --resume`. Las personas siguen el orden round-robin, así que una corrida parcial queda balanceada entre departamentos. Para ver el avance (n de 280 por versión), usar el dashboard o contar las líneas del archivo.
- Resúmenes: `scripts/06_analyze.py` escribe `summary_A.json`, `summary_B.json` y `summary_AB.json` con las filas disponibles. El dashboard no depende de esos archivos: calcula las cifras directamente desde los JSONL.
- Pendientes:
  1. Completar las corridas A y B hasta 280 personas cada una.
  2. Redactar el análisis del Analista con el modelo (`scripts/06_analyze.py` sin `--sin-llm`) y comprobar que `analisis_*.json` no queden en `null`.
  3. Repetir `scripts/04_benchmark.py` con el prompt por componentes vigente.
  4. Corridas con el modelo `9b` y con `--parallel 2`. Sin medir.
  5. Rúbrica humana de calidad en español: 10 respuestas, puntaje mínimo 3.5 de 5. Requiere revisión de una persona.

## Configuración local

- Copiar `.env.example` a `.env` y ajustar los valores. `.env` no se versiona.
- `LLM_BASE_URL` apunta al servidor local (Ollama en `http://localhost:11434/v1` por defecto).
- `NVIDIA_API_KEY` solo se usa si `USE_FALLBACK=1`.
