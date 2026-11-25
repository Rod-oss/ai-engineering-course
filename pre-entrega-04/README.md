# Pre-entrega 4: sistema RAG escalable en la nube con Pinecone

Módulo de recuperación que indexa documentos técnicos en **Pinecone Serverless** y los busca con un **recuperador híbrido** que combina búsqueda semántica (embeddings) y léxica (BM25) mediante `EnsembleRetriever`. Incluye un script de evaluación con **Recall@5** y **Precision@5** sobre un golden set.

## Arquitectura

```
data/*.md + catalogo.json
        │
        ▼
documents.py ── chunking por tokens + metadatos ──┬──► ingest.py ──► Pinecone (namespace kestrel-docs)
                                                  │
                                                  └──► BM25 (en memoria)

consulta ──► RAGSystem ──► EnsembleRetriever ──┬── Pinecone (semántico, top 5)
                                               └── BM25 (léxico, top 5)
                                                     │
                                                     ▼
                                     fusión RRF ──► top 5 final
```

## Componentes

| Archivo | Responsabilidad |
|---|---|
| `config.py` | Configuración validada, embeddings, cliente de Pinecone y constantes |
| `documents.py` | Carga y fragmentación; única fuente de fragmentos para Pinecone y BM25 |
| `setup_index.py` | Crea el índice serverless si no existe y verifica su dimensión |
| `ingest.py` | Sube los fragmentos con texto y metadatos al namespace |
| `rag_system.py` | Clase `RAGSystem` con `EnsembleRetriever`, filtros y modos de búsqueda |
| `golden_set.json` | 5 preguntas con su documento esperado |
| `evaluate.py` | Calcula Recall@5 y Precision@5 en tres modos |
| `resultados_evaluacion.json` | Detalle de la última evaluación |

## Dataset y metadatos

`data/` contiene 8 documentos de una plataforma **ficticia**, Kestrel: arquitectura, API, despliegues, incidentes, seguridad, datos y respaldos, monitoreo y onboarding. Cada documento tiene su categoría y etiquetas en `data/catalogo.json`.

Cada vector en Pinecone guarda estos metadatos:

| Campo | Ejemplo | Uso |
|---|---|---|
| `text` | Contenido del fragmento | Evita consultar otra base de datos para obtener el texto |
| `chunk_id` | `datos-00` | ID estable, compartido con BM25 para eliminar duplicados |
| `source` | `datos.md` | Fuente del fragmento y base de la evaluación |
| `titulo` | `Datos, respaldos y recuperación de Kestrel` | Contexto del documento |
| `categoria` | `operaciones` | Filtros por metadatos |
| `etiquetas` | `["respaldos", "recuperacion"]` | Clasificación temática |
| `secciones` | `["Política de respaldos", ...]` | Equivalente a la página en documentos Markdown |
| `chunk`, `tokens` | `0`, `412` | Posición y tamaño del fragmento |

## Chunking

`RecursiveCharacterTextSplitter.from_tiktoken_encoder` con **600 tokens y 60 de solapamiento**, dentro del rango de 500 a 800 recomendado. Los separadores priorizan las secciones de Markdown (`## `) y luego los párrafos, para no mezclar temas. Resultado: 12 fragmentos de entre 42 y 586 tokens (promedio 395).

## Recuperador híbrido

`RAGSystem` encapsula un `EnsembleRetriever` con:

- **Recuperador semántico:** `PineconeVectorStore` en el namespace `kestrel-docs`, top 5.
- **Recuperador léxico:** `BM25Retriever` sobre los mismos fragmentos, top 5, con una tokenización que pasa a minúsculas y conserva términos técnicos como `kestrel-cli` o `pedidos.muertos`.
- **Fusión:** Reciprocal Rank Fusion con pesos 0.5 y 0.5, deduplicación por `chunk_id` y recorte a los 5 primeros.

También admite filtrar por categoría (`rag.buscar(consulta, categoria="seguridad")`) y buscar en los modos `vectorial`, `lexico` o `hibrido`.

## Cómo replicar el índice

1. Crea una cuenta gratuita en [Pinecone](https://app.pinecone.io) y copia tu API key.
2. Obtén una clave de Gemini en [Google AI Studio](https://aistudio.google.com/apikey), o usa una de OpenAI.
3. Desde la carpeta `pre-entrega-04`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # coloca tus claves en .env
python setup_index.py       # crea el índice serverless (aws, us-east-1, métrica coseno)
python ingest.py            # sube los fragmentos al namespace kestrel-docs
python rag_system.py        # demostración de los modos y del filtro por categoría
python evaluate.py          # evaluación de métricas
```

`setup_index.py` **mide la dimensión real** del modelo de embeddings antes de crear el índice y, si el índice ya existe, verifica que coincida. Con `gemini-embedding-001` la dimensión es **3072**, no 1536, que es la de OpenAI `text-embedding-3-small`. Así se evita el error de dimensiones no coincidentes. `ingest.py --rebuild` vacía el namespace y reindexa.

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `OPENAI_API_KEY` | Clave del proveedor de embeddings | Clave de Gemini |
| `OPENAI_BASE_URL` | Dirección de la API (vacía para OpenAI real) | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `OPENAI_EMBEDDING_MODEL` | Modelo de embeddings | `gemini-embedding-001` |
| `OPENAI_TIMEOUT` | Segundos máximos por llamada | `30` |
| `PINECONE_API_KEY` | Clave de Pinecone | |
| `INDEX_NAME` | Nombre del índice (minúsculas, números y guiones) | `kestrel-hybrid-rag` |

El archivo `.env` está excluido del repositorio. Las claves se validan con Pydantic y se manejan como `SecretStr`.

## Evaluación

El golden set combina preguntas conceptuales, de términos exactos y una paráfrasis que describe un concepto sin usar sus palabras clave.

- **Recall@5:** 1 si el documento esperado aparece entre los 5 recuperados.
- **Precision@5:** proporción de los 5 recuperados que pertenece a un documento relevante.
- **Precisión máxima posible:** como varios documentos tienen solo uno o dos fragmentos, la precisión no puede llegar a 1. Por ejemplo, con un solo fragmento relevante el máximo es 1/5 = 0.20.

### Resultados

```
Pregunta  Tipo              vectorial          lexico            hibrido
                         R@5  P@5  pos.     R@5  P@5  pos.     R@5  P@5  pos.
q1        conceptual       1 0.40     1       1 0.20     1       1 0.20     1
q2        termino_exacto   1 0.20     1       1 0.20     1       1 0.20     1
q3        termino_exacto   1 0.20     1       1 0.20     1       1 0.20     1
q4        parafrasis       1 0.40     1       1 0.20     2       1 0.40     1
q5        conceptual       1 0.40     1       1