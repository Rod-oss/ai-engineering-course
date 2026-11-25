# Pre-entrega 2: pipeline de procesamiento validado

Pipeline de extracción de entidades técnicas construido con LangChain (LCEL). Recibe un texto sin procesar, como un log de error o una descripción de arquitectura, y devuelve un objeto validado con Pydantic que contiene las tecnologías mencionadas, el nivel de criticidad y un resumen técnico.

## Cómo funciona

```
ChatPromptTemplate → ChatOpenAI.with_structured_output(ExtraccionTecnica) → validación
└──────────────────────── .with_retry(3 intentos, backoff exponencial) ────────────────┘
```

1. **Prompt modular** (`ChatPromptTemplate`): recibe el texto en `{texto}` y las reglas de formato en `{instrucciones_formato}`, inyectadas con `.partial()`. No se usan f-strings.
2. **Salida estructurada**: `.with_structured_output(..., method="json_schema", include_raw=True)` obliga al modelo a responder con el esquema de `ExtraccionTecnica` y conserva la respuesta original para revisar el `finish_reason`.
3. **Validación**: un paso adicional rechaza respuestas cortadas (`finish_reason="length"`), JSON mal formado u objetos que no cumplen el esquema, lanzando `SalidaInvalidaError`.
4. **Resiliencia**: `.with_retry()` reintenta hasta 3 veces ante salidas inválidas, respuestas cortadas, límite de tasa (429), errores de conexión y errores 5xx. Si se agotan los intentos, `process_text()` lanza un `PipelineError` controlado.
5. **Ejecución asíncrona**: `process_text(text)` ejecuta la cadena con `.ainvoke()`.

## Esquema de salida (`schemas.py`)

| Campo | Tipo | Restricciones |
|---|---|---|
| `tecnologias` | `list[str]` | Al menos un elemento; se eliminan espacios, vacíos y duplicados |
| `nivel_de_criticidad` | Enum | Solo `baja`, `media` o `alta` |
| `resumen_tecnico` | `str` | Entre 10 y 300 caracteres |

## Proveedor

Se usa `ChatOpenAI` apuntando a la API de Gemini compatible con OpenAI (modelo `gemini-3.5-flash-lite`, plan gratuito), con las mismas variables de entorno de la Pre-entrega 1. Para usar OpenAI real basta con cambiar los valores en `.env`, sin modificar código.

## Instalación

Desde la carpeta `pre-entrega-02`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Después, coloca tu clave en `OPENAI_API_KEY` dentro de `.env`.

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `OPENAI_API_KEY` | Clave del proveedor compatible con OpenAI | Clave de Gemini |
| `OPENAI_BASE_URL` | Dirección de la API (vacía para OpenAI real) | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `OPENAI_MODEL` | Modelo a utilizar | `gemini-3.5-flash-lite` |
| `OPENAI_TIMEOUT` | Segundos máximos por llamada | `30` |

El archivo `.env` está excluido del repositorio mediante `.gitignore`.

## Ejecución

```bash
python test_pipeline.py
```

El script ejecuta cuatro casos:

| Caso | Entrada | Qué demuestra |
|---|---|---|
| `log_error` | Log de error en producción | Extracción con criticidad alta |
| `arquitectura` | Descripción de arquitectura | Extracción con criticidad baja |
| `ambiguo` | Texto vago, sin tecnologías concretas | Prueba de estrés del validador |
| `tokens_insuficientes` | Límite de 30 tokens a propósito | Detección de `finish_reason="length"`, reintentos y error controlado |

Los tres primeros se ejecutan en paralelo con `asyncio.gather`.

## Ejemplo de salida

**`log_error`**

```json
{
  "tecnologias": ["PostgreSQL", "FastAPI", "Celery", "Redis"],
  "nivel_de_criticidad": "alta",
  "resumen_tecnico": "Fallo de conexion en PostgreSQL por exceso de clientes genera errores 503 en FastAPI y acumula tareas en Celery y Redis."
}
```

**`arquitectura`**

```json
{
  "tecnologias": ["React", "GraphQL", "Node.js", "Apollo Server", "MongoDB Atlas", "Amazon S3", "CloudFront", "AWS Lambda"],
  "nivel_de_criticidad": "baja",
  "resumen_tecnico": "Se evalúa la migración de trabajos programados a AWS Lambda en la arquitectura actual basada en React, Node.js y MongoDB."
}
```

**`ambiguo`**

```json
{
  "tecnologias": ["base de datos"],
  "nivel_de_criticidad": "media",
  "resumen_tecnico": "Se registra una degradación intermitente del rendimiento sin errores claros en los registros."
}
```

**`tokens_insuficientes`**: el pipeline realizó 3 intentos y terminó con un error controlado:

```
Error controlado: Sin extracción válida tras 3 intento(s): respuesta cortada por límite de tokens (finish_reason=length)
```

## Resultado de la prueba de estrés

Con el texto ambiguo, el validador no lanzó ninguna excepción: el modelo devolvió un objeto válido en el primer intento. Sin embargo, para cumplir la restricción de que la lista de tecnologías no esté vacía, usó el término genérico "base de datos" en lugar de una tecnología concreta. La restricción garantiza la estructura, pero no puede garantizar que el contenido sea específico.

## Decisiones técnicas

- **`include_raw=True`**: permite revisar el `finish_reason` de la respuesta original antes de aceptar el objeto.
- **Respuesta cortada**: con `method="json_schema"`, el SDK de OpenAI detecta el `finish_reason="length"` y lanza `LengthFinishReasonError`, que se incluye entre los errores reintentables. El paso de validación propio cubre además el caso del método `function_calling`.
- **Reintentos solo ante errores recuperables**: errores como una clave inválida no se reintentan.
- **Reintentos internos del SDK desactivados** (`max_retries=0`) para que no se sumen a los de `.with_retry()`.
- **Temperatura 0**: respuestas más estables para una tarea de extracción.
- **Logs**: cada intento queda registrado, y los reintentos aparecen como advertencias.

## Limitaciones conocidas

- Como muestra la prueba de estrés, un texto sin tecnologías concretas produce términos genéricos.
- Los errores 429 y de conexión están contemplados en los reintentos, pero no se provocaron en las pruebas para no agotar la cuota gratuita. El mecanismo de reintento se verificó con respuestas cortadas.
- Los límites gratuitos de Gemini dependen del proyecto de Google Cloud y pueden cambiar.

## Estructura

```
pre-entrega-02/
├── README.md
├── requirements.txt
├── .env.example
├── schemas.py
├── chain.py
└── test_pipeline.py
```