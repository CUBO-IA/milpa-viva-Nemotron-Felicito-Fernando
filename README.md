# Milpa Viva

**Inteligencia agrícola para comprender mejor a los productores salvadoreños.**

Milpa Viva es una plataforma que combina inteligencia artificial, personas sintéticas y datos agrícolas para explorar cómo los productores podrían interpretar y responder a alertas climáticas, información de mercado y programas de apoyo al sector agrícola.

A través de agricultores sintéticos basados en el conjunto de datos **Nemotron Personas El Salvador**, la plataforma permite analizar distintos mensajes y propuestas, identificar posibles barreras de comprensión y comparar alternativas de comunicación antes de llevarlas a los productores.

## ¿Por qué Milpa Viva?

Una alerta climática o una recomendación de mercado puede ser técnicamente correcta y, aun así, no resultar clara o relevante para quien la recibe. La forma de comunicar la información influye en cómo se comprende y en las decisiones que las personas consideran.

Milpa Viva ofrece un entorno para explorar esas respuestas desde distintas perspectivas. De esta manera, instituciones, organizaciones y equipos que trabajan con el sector agrícola pueden revisar sus mensajes, reconocer posibles barreras y diseñar comunicaciones más cercanas a las necesidades de los productores.

## ¿Cómo funciona?

Milpa Viva compara dos versiones de un mismo programa o mensaje:

- **Versión A:** propuesta de comunicación inicial.
- **Versión B:** propuesta ajustada a partir de las barreras identificadas, con un lenguaje más claro y accesible.

Cada agricultor sintético recibe información contextualizada sobre clima, precios y programas agrícolas correspondientes a su departamento. A continuación, expresa en su propia voz cómo interpreta la información y cuál sería su posible respuesta: comprenderla, adoptar la propuesta, considerarla más adelante o no adoptarla. También identifica las razones que influyen en su decisión.

Un agente analista consolida las respuestas, calcula indicadores por departamento y prepara una síntesis de los principales hallazgos para su visualización en el dashboard.

Las personas sintéticas proceden del conjunto de datos [nvidia/Nemotron-Personas-El-Salvador](https://huggingface.co/datasets/nvidia/Nemotron-Personas-El-Salvador), publicado bajo licencia CC-BY-4.0. El panel de referencia está compuesto por 280 perfiles: 20 por cada uno de los 14 departamentos de El Salvador, con muestreo estratificado por edad y escolaridad y una semilla de selección fija.

## Arquitectura

### Agentes especializados

Milpa Viva organiza el procesamiento mediante cuatro agentes con responsabilidades específicas:

| Agente | Responsabilidad | Resultado |
| --- | --- | --- |
| **Clima** | Interpreta el pronóstico según departamento, cultivo y escala de análisis. | Mensajes de alerta climática contextualizados por segmento. |
| **Mercado** | Analiza el boletín de precios y la información del segmento agrícola. | Información de precios y recomendaciones de mercado. |
| **Agricultor** | Interpreta los mensajes de clima y mercado junto con el programa asignado a cada perfil. | Comprensión, decisión, barreras y respuesta expresada en voz propia. |
| **Analista** | Consolida y examina los resultados de las simulaciones. | Indicadores por departamento y síntesis de hallazgos. |

Los agentes Clima y Mercado preparan información por segmento, que se utiliza en las distintas versiones de los programas. El agente Agricultor procesa las respuestas de cada perfil individualmente. Finalmente, el Analista reúne los resultados y genera indicadores y contenido para el dashboard.

Las respuestas de los agentes siguen esquemas JSON definidos y validados con Pydantic (`src/milpa/schemas.py`). Los indicadores numéricos se procesan con pandas para mantener consistencia entre las cifras y los resúmenes presentados.

### Recuperación de información (RAG)

La arquitectura RAG permite que los agentes consulten información contextual antes de generar sus respuestas.

Los documentos de `data/static/` —pronósticos, boletines de mercado, programas y calendario agrícola— se dividen en fragmentos organizados por encabezados. Cada fragmento incorpora metadatos sobre su tipo, zona geográfica (Occidental, Central, Paracentral u Oriental) y versión (A, B o todas).

Los embeddings se generan con `intfloat/multilingual-e5-small` y se almacenan en Chroma (`chroma_db/`). Los agentes Clima, Mercado y Agricultor consultan este índice para recuperar información relacionada con la zona y el contexto de cada perfil.

### Modelos de lenguaje e inferencia local

Milpa Viva utiliza **NVIDIA Nemotron 3 Nano 4B**, en formato GGUF Q4_K_M, como modelo de lenguaje para el procesamiento local.

La arquitectura utiliza un servidor de inferencia compatible con la API de OpenAI, como **Ollama** o **LM Studio**, y el backend Vulkan para la ejecución con aceleración gráfica compatible.

La configuración del servidor y del modelo se administra mediante las variables `LLM_BASE_URL` y `LLM_MODEL` en el archivo `.env`. Esta separación permite configurar el entorno de inferencia sin modificar la lógica de los agentes.

La configuración también contempla **Nemotron Nano 9B v2 (GGUF Q4_K_M)** y la API de NVIDIA como alternativas de configuración del modelo y del servicio de inferencia.

Las solicitudes utilizan esquemas JSON cuando el servidor los admite. Las respuestas se validan con Pydantic y cuentan con un mecanismo de reintento ante errores de validación.

## Estructura del repositorio

```text
milpa-viva/
├── README.md  config.yaml  requirements.txt  .env.example
├── data/
│   ├── raw/            # Dataset original
│   ├── panel/          # Panel de personas sintéticas
│   ├── static/         # Pronósticos, precios, programas y calendario
│   └── geo/            # Información geográfica de departamentos
├── src/milpa/
│   ├── config.py  llm.py  panel.py  rag.py  schemas.py  simulate.py
│   ├── agents/         # clima.py mercado.py agricultor.py analista.py
│   └── prompts/        # Instrucciones de cada agente
├── scripts/            # Descarga, preparación, indexación y análisis
├── results/            # Resultados de simulaciones y análisis
├── app/dashboard.py    # Dashboard interactivo con Streamlit
├── docs/               # Documentación y decisiones de diseño
└── tests/
```

Los prompts de los agentes se mantienen en archivos `.md`, lo que facilita revisar y ajustar sus instrucciones de forma independiente. Los parámetros del panel, el modelo, RAG y el modo de ejecución se administran desde `config.yaml`. Las credenciales y demás valores privados se configuran en `.env`, archivo que no se incorpora al control de versiones.

## Instalación y configuración

### 1. Preparar el entorno

Se requiere Python 3.12 o superior.

```bash
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### 2. Configurar el modelo local

Milpa Viva puede utilizar Ollama o LM Studio como servidor de inferencia.

Con Ollama en Windows:

```powershell
winget install Ollama.Ollama
setx OLLAMA_VULKAN 1
setx OLLAMA_NUM_PARALLEL 2
setx OLLAMA_KEEP_ALIVE 2h
```

Después de iniciar Ollama, descarga el modelo:

```powershell
ollama pull hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M
```

Para iniciar una consulta de prueba:

```powershell
ollama run hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M "Explicá en dos líneas qué es la canícula"
```

El endpoint compatible con OpenAI de Ollama es `http://localhost:11434/v1`.

Con LM Studio, carga el mismo modelo GGUF, selecciona el backend Vulkan e inicia el servidor local. Su endpoint compatible con OpenAI utiliza por defecto `http://localhost:1234/v1`.

### 3. Variables de entorno

Configura el archivo `.env` con los parámetros del servidor y del modelo:

```dotenv
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M
LLM_API_KEY=
USE_FALLBACK=0
FALLBACK_BASE_URL=https://integrate.api.nvidia.com/v1
FALLBACK_MODEL=nvidia/nvidia-nemotron-nano-9b-v2
NVIDIA_API_KEY=
```

La clave `NVIDIA_API_KEY` se configura para utilizar el servicio de inferencia de NVIDIA.

### 4. Preparar los datos

Descarga el conjunto de datos, construye el panel de personas sintéticas e indexa los documentos de referencia:

```bash
python scripts/01_download.py
python scripts/02_build_panel.py --por-depto 20 --seed 42
python scripts/03_ingest_rag.py
```

La configuración de referencia genera un panel de 280 perfiles, distribuidos entre los 14 departamentos. El parámetro `--seed` permite reproducir la misma selección de perfiles.

### 5. Evaluar el modelo

El benchmark permite observar métricas de ejecución y calidad de las respuestas estructuradas:

```bash
python scripts/04_benchmark.py --n 20 --backend ollama --model 4b
```

Los resultados incluyen latencia, tokens por segundo y porcentaje de respuestas JSON válidas, y se almacenan en `results/bench.csv`.

### 6. Ejecutar las simulaciones y el análisis

Ejecuta las simulaciones para las versiones A y B:

```bash
python scripts/05_run.py --version A --resume
python scripts/05_run.py --version B --resume
```

También es posible seleccionar departamentos y definir el número de perfiles por departamento:

```bash
python scripts/05_run.py --version A --deptos Morazán "La Unión" --por-depto 2
```

Para consolidar los resultados y generar el análisis:

```bash
python scripts/06_analyze.py
```

El parámetro `--parallel K` permite configurar el procesamiento paralelo. La opción `--resume` permite continuar una corrida utilizando los resultados previamente registrados.

### 7. Consultar el dashboard

Inicia la aplicación con Streamlit:

```bash
streamlit run app/dashboard.py
```

El dashboard presenta los resultados de las simulaciones y los indicadores organizados por departamento. También permite ejecutar muestras de personas mediante la opción **Correr en vivo**, utilizando el servidor de inferencia configurado.

Un enlace con el parámetro `?uuid=...` permite abrir directamente la ficha de un perfil.

### 8. Ejecutar las pruebas

```bash
pytest -q
```

## Los cuatro ejes tecnológicos

**1. Modelos de lenguaje e inferencia local**

Integración de NVIDIA Nemotron 3 Nano 4B mediante servidores de inferencia compatibles con OpenAI, con configuración flexible del modelo y del entorno de ejecución.

**2. Recuperación aumentada por generación (RAG)**

Consulta contextual de pronósticos, boletines de precios, programas y calendario agrícola. La recuperación considera el tipo de documento, la zona geográfica y la versión del programa.

**3. Agentes especializados**

Cuatro agentes colaboran en el análisis: Clima y Mercado preparan información contextual, Agricultor interpreta los mensajes desde la perspectiva de cada perfil y Analista consolida los resultados para su interpretación.

**4. Procesamiento local y arquitectura modular**

Los datos del panel, los documentos de referencia, los embeddings y el procesamiento de los agentes se organizan en una arquitectura modular. La configuración de los servicios de inferencia permite integrar distintos entornos de ejecución.

## Desarrollo asistido por inteligencia artificial

Durante el desarrollo de Milpa Viva se utilizaron herramientas de inteligencia artificial como apoyo para la construcción, revisión y evolución de la solución:

- **Hermes Agent**, utilizando el modelo gratuito **LongCant 2.5**.
- **FreeBuff**, utilizando **DeepSeek 4.1 Flash**.

Estas herramientas formaron parte del flujo de trabajo de desarrollo asistido por IA.

## Licencia y fuentes de datos

- **Nemotron Personas El Salvador:** [nvidia/Nemotron-Personas-El-Salvador](https://huggingface.co/datasets/nvidia/Nemotron-Personas-El-Salvador), licencia CC-BY-4.0. Los nombres de visualización se generan de forma determinista y no proceden directamente del conjunto de datos.
- **Información agrícola:** los pronósticos, precios y programas utilizados como contexto se organizan en los archivos de referencia de `data/static/`.
