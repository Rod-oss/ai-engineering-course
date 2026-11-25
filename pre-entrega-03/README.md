# Pre-entrega 3: sistema de recuperación semántica local (RAG)

Sistema RAG de extremo a extremo: indexa documentos en una base vectorial local con ChromaDB y responde preguntas usando **exclusivamente** la información recuperada. Si la respuesta no está en los documentos, responde "No lo sé." La salida se valida con Pydantic e incluye las fuentes utilizadas.

## Cómo funciona

```
INGESTA (ingest.py, una sola vez)
data/*.md → fragmentos de 500 tokens (50 de solapamiento) → embeddings → ChromaDB (./vectorstore)

CONSULTA (rag.py → get_rag_response)
pregunta → embedding → top 4 fragmentos → prompt con contexto → LLM → PydanticOutputParser → fuentes verificadas
```

## Dataset

La carpeta `data/` contiene cuatro documentos de una plataforma **ficticia**, Kestrel, de la empresa ficticia Nubaria: arquitectura, guía de incidentes, política de despliegues y API. Se eligió un tema inventado a propósito: como el modelo no puede conocer esta información de antemano, la prueba de "no alucinar" es verificable.

## Componentes

| Archivo | Responsabilidad |
|---|---|
| `config.py` | Crea en un solo lugar los embeddings, la base vectorial y el LLM |
| `ingest.py` | Lee `data/`, fragmenta por tokens y persiste en ChromaDB |
| `schemas.py` | `RespuestaRAG` (salida del modelo) y `ResultadoRAG` (resultado final) |
| `rag.py` | Cadena LCEL y función asíncrona `get_rag_response(query)` |
| `test_rag.py` | Pruebas con preguntas respondibles y una pregunta trampa |
| `resultados_pruebas.json` | Evidencia de la última ejecución de las pruebas |

## Estrategia de chunking e ingesta

- **`RecursiveCharacterTextSplitter.from_tiktoken_encoder`** con `chunk_size=500` y `chunk_overlap=50`, medidos en **tokens** (codificación `cl100k_base`, usada como aproximación para Gemini).
- **Separadores en orden de prioridad:** secciones de Markdown (`## `), párrafos, líneas, oraciones y palabras. Así cada fragmento conserva un tema completo.
- **Resultado:** 9 fragmentos de entre 73 y 462 tokens (promedio 327). Ninguno llega al máximo de 500 porque los documentos son cortos y el splitter prioriza no partir secciones, lo que preserva el contexto semántico.
- **Metadatos:** cada fragmento guarda su archivo de origen, su número y una referencia como `incidentes.md#1`.
- **Persistencia:** si la colección ya tiene fragmentos, la ingesta se omite. `python ingest.py --rebuild` la reconstruye. Los fragmentos tienen IDs estables (hash del contenido), así que reindexar no duplica datos.

## Recuperación y generación

`get_rag_response(query)` ejecuta de forma asíncrona (`.ainvoke()`) una cadena LCEL que:

1. Busca por similitud los `top_k = 4` fragmentos más cercanos a la pregunta.
2. Inserta los fragmentos, con sus referencias, en un `ChatPromptTemplate`.
3. Llama al LLM con un prompt que funciona como filtro de veracidad: responder solo con el contexto y decir "No lo sé." si la respuesta no está.
4. Convierte la respuesta en un objeto `RespuestaRAG` mediante `PydanticOutputParser`, con hasta 3 intentos si el JSON es inválido.

## Validación y fuentes

- `RespuestaRAG` exige coherencia: si `encontrada` es verdadero, debe haber al menos una fuente; si es falso, la respuesta se fija en "No lo sé." y sin fuentes.
- El código **verifica las fuentes citadas**: descarta cualquier referencia que no se haya recuperado realmente, para que el modelo no pueda inventarlas.
- **Mismo modelo de embeddings para indexar y consultar:** ambos usan la función `crear_embeddings()`, y la colección guarda el nombre del modelo con el que se indexó. Si al consultar se usa otro, el sistema se detiene y pide reindexar.

## Proveedor

Se usan modelos gratuitos de Gemini a través de su API compatible con OpenAI:

| Uso | Modelo |
|---|---|
| Embeddings | `gemini-embedding-001` |
| Generación | `gemini-3.5-flash-lite` |

Para usar OpenAI real, basta con cambiar las variables en `.env` (por ejemplo, `text-embedding-3-small`) y ejecutar `python ingest.py --rebuild`.

## Instalación

Desde la carpeta `pre-entrega-03`:

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
| `OPENAI_API_KEY` | Clave del proveedor | Clave de Gemini |
| `OPENAI_BASE_URL` | Dirección de la API (vacía para OpenAI real) | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `OPENAI_MODEL` | Modelo de generación | `gemini-3.5-flash-lite` |
| `OPENAI_EMBEDDING_MODEL` | Modelo de embeddings | `gemini-embedding-001` |
| `OPENAI_TIMEOUT` | Segundos máximos por llamada | `30` |

El archivo `.env` y la carpeta `vectorstore/` están excluidos del repositorio.

## Ejecución

```bash
python ingest.py      # indexa los documentos (solo la primera vez)
python test_rag.py    # ejecuta las pruebas
```

## Resultados de las pruebas

| Prueba | Pregunta | Resultado esperado | Resultado |
|---|---|---|---|
| Un documento | ¿Qué hacer si en un despliegue canario la tasa de errores supera el límite? | Respuesta con fuentes | ✅ Citó `despliegues.md#1` |
| Varios documentos | ¿Qué base usa el servicio de pedidos y qué severidad tiene si deja de aceptar escrituras? | Respuesta con fuentes | ✅ Citó `arquitectura.md` e `incidentes.md` |
| Pregunta trampa | ¿Cuánto cuesta al mes el plan empresarial de la API? | "No lo sé." | ✅ "No lo sé.", sin fuentes |

En la pregunta trampa el sistema recuperó fragmentos de `api.md`, que tratan sobre la API, pero ninguno menciona precios, y el modelo no inventó una respuesta. El detalle completo de la ejecución está en `resultados_pruebas.json`.

Ejemplo de salida de la pregunta trampa:

```json
{
  "pregunta": "¿Cuánto cuesta al mes el plan empresarial de la API de Kestrel?",
  "respuesta": "No lo sé.",
  "encontrada": false,
  "fuentes": [],
  "fragmentos_recuperados": ["api.md#1", "arquitectura.md#0", "api.md#0", "despliegues.md#0"]
}
```

## Limitaciones conocidas

- El conteo de tokens usa el codificador de OpenAI como aproximación; Gemini puede contar ligeramente distinto.
- Los métodos asíncronos del vector store de LangChain para Chroma ejecutan internamente la búsqueda local en un hilo aparte; la llamada al LLM y a la API de embeddings sí es asíncrona de extremo a extremo.
- Las respuestas dependen de que la recuperación traiga los fragmentos correctos: con documentos más grandes convendría evaluar la recuperación con métricas, como se hará en la Pre-entrega 4.

## Estructura

```
pre-entrega-03/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── data/
│   ├── api.md
│   ├── arquitectura.md
│   ├── despliegues.md
│   └── incidentes.md
├── config.py
├── schemas.py
├── ingest.py
├── rag.py
├── test_rag.py
└── resultados_pruebas.json
```