# Pre-entrega 1: cliente de LLM robusto y asíncrono

Implementación de un *Unified Async LLM Client* en Python 3.12: una interfaz común para trabajar con proveedores compatibles con OpenAI y con Anthropic, con llamadas asíncronas, streaming de tokens, validación con Pydantic y manejo de errores con reintentos.

## Qué incluye

| Requisito | Implementación |
|---|---|
| Intercambiabilidad | `AsyncLLMManager` (`manager.py`) crea el cliente según la variable `LLM_PROVIDER` (patrón Factory) |
| Interfaz común | Clase abstracta `BaseLLMClient` (`base_client.py`) |
| Proveedores | `OpenAIClient` con `AsyncOpenAI` y `AnthropicClient` con `AsyncAnthropic` |
| Asincronía | Todas las llamadas usan `async`/`await` y el SDK asíncrono oficial |
| Streaming | Método `stream()`: generador asíncrono con `yield` dentro de `async for` |
| Validación | `ChatMessage`, `ModelConfig` (temperatura de 0 a 2, `max_tokens`, etc.), `ProviderSettings` y `ModelResponse` en `schemas.py` |
| Resiliencia | Reintentos con backoff exponencial ante errores temporales y respuesta estructurada ante cualquier error |

## Arquitectura

```
main.py
   │
   ▼
AsyncLLMManager  (manager.py)   ← lee LLM_PROVIDER y crea el cliente
   │
   ▼
BaseLLMClient  (base_client.py) ← interfaz común, reintentos, timeouts y errores
   ├── OpenAIClient     (openai_client.py)    → AsyncOpenAI
   └── AnthropicClient  (anthropic_client.py) → AsyncAnthropic
```

El resto del programa solo usa `generate()` y `stream()`. Las diferencias entre SDKs (formato de la respuesta, streaming, mensajes `system`, parámetros obligatorios) quedan ocultas dentro de cada cliente.

## Proveedores utilizados

Por restricciones de presupuesto, y con aprobación del tutor, se usan proveedores gratuitos compatibles con los SDKs oficiales:

| Cliente | SDK oficial | Proveedor configurado | Modelo |
|---|---|---|---|
| `OpenAIClient` | `openai` (`AsyncOpenAI`) | Gemini API, endpoint compatible con OpenAI | `gemini-3.5-flash-lite` |
| `AnthropicClient` | `anthropic` (`AsyncAnthropic`) | Ollama local, compatible con la API de Anthropic | `qwen2.5:1.5b` |

**Para usar OpenAI o Anthropic reales no hay que modificar código:** basta con poner la clave correspondiente en `.env`, dejar vacía la variable `*_BASE_URL` y elegir un modelo de ese proveedor.

## Requisitos previos

- Python 3.12
- Una clave de Gemini API (gratuita en [Google AI Studio](https://aistudio.google.com/apikey)) o de OpenAI
- [Ollama](https://ollama.com) en ejecución con el modelo `qwen2.5:1.5b`, o una clave de Anthropic

En el Codespace de este repositorio, Ollama y el modelo se instalan y se inician automáticamente (ver `.devcontainer/`).

## Instalación

Desde la carpeta `pre-entrega-01`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Después, edita `.env` y coloca tu clave en `OPENAI_API_KEY`.

Si no usas el Codespace, inicia Ollama en otra terminal y descarga el modelo:

```bash
ollama serve
ollama pull qwen2.5:1.5b
```

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `LLM_PROVIDER` | Proveedor por defecto del manager | `openai` o `anthropic` |
| `OPENAI_API_KEY` | Clave del proveedor compatible con OpenAI | Clave de Gemini |
| `OPENAI_BASE_URL` | Dirección de la API (vacía para OpenAI real) | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `OPENAI_MODEL` | Modelo a utilizar | `gemini-3.5-flash-lite` |
| `OPENAI_TIMEOUT` | Segundos máximos por llamada | `30` |
| `ANTHROPIC_API_KEY` | Clave del proveedor compatible con Anthropic | `ollama` (Ollama no la valida) |
| `ANTHROPIC_BASE_URL` | Dirección de la API (vacía para Anthropic real) | `http://127.0.0.1:11434` |
| `ANTHROPIC_MODEL` | Modelo a utilizar | `qwen2.5:1.5b` |
| `ANTHROPIC_TIMEOUT` | Segundos máximos por llamada | `120` (el modelo local corre sin GPU) |

El archivo `.env` está excluido del repositorio mediante `.gitignore`. Las claves se manejan con `SecretStr` para que no aparezcan en logs ni mensajes de error.

## Ejecución

```bash
python main.py
```

El script pregunta "¿Qué es la entropía?" y demuestra, en una sola ejecución:

1. Que `AsyncLLMManager()` elige el cliente según `LLM_PROVIDER`.
2. Generación en modo normal y en streaming con los dos proveedores.
3. Que Pydantic rechaza una temperatura fuera de rango.
4. Un error permanente (clave inválida): se devuelve un error controlado sin reintentar.
5. Un error temporal (servidor inaccesible): se reintenta con backoff exponencial y luego se devuelve un error controlado.

## Ejemplo de salida

```
======================================================================
LLM_PROVIDER=openai -> AsyncLLMManager() creó OpenAIClient
======================================================================

======================================================================
Proveedor: openai | Cliente: OpenAIClient | Modelo: gemini-3.5-flash-lite
======================================================================

[Modo normal]
La entropía es una magnitud física que mide el grado de desorden y la pérdida de energía útil en un sistema termodinámico. Según la segunda ley de la termodinámica, este valor tiende a aumentar de manera irreversible en el universo con el paso del tiempo. En términos sencillos, representa la tendencia natural de las cosas a pasar de un estado organizado a uno más caótico.
(tokens: 22 de entrada, 78 de salida | fin: stop)

[Modo streaming]
La entropía es una magnitud física que mide el grado de desorden y la aleatoriedad en un sistema termodinámico. Según la segunda ley de la termodinámica, la entropía del universo siempre tiende a aumentar con el tiempo en los procesos espontáneos. En términos sencillos, representa la energía de un sistema que ya no está disponible para realizar un trabajo útil.

======================================================================
Proveedor: anthropic | Cliente: AnthropicClient | Modelo: qwen2.5:1.5b
======================================================================

[Modo normal]
La entropía es un concepto fundamental en la física, principalmente en la termodinámica, que se refiere a la cantidad de información necesaria para describir un sistema en movimiento determinado.
(tokens: 34 de entrada, 44 de salida | fin: end_turn)

[Modo streaming]
La entropía es un concepto utilizado en física y ciencias de la computación para medir la incertidumbre o la cantidad de información necesaria para predecir el resultado de un evento en un espacio de estado.

======================================================================
Pruebas de validación y resiliencia
======================================================================

1. Pydantic rechaza una temperatura fuera de rango (3.0):
   Rechazada: Input should be less than or equal to 2

2. Clave inválida (error permanente, no se reintenta):
   Error de la API (400): Please pass a valid API key

3. Servidor inaccesible (error temporal, se reintenta con backoff):
   WARNING [anthropic] Error de conexión: Connection error. | Reintento 1 de 2 en 1.4 s
   WARNING [anthropic] Error de conexión: Connection error. | Reintento 2 de 2 en 2.2 s
   Error de conexión: Connection error.

Validación terminada: ningún error detuvo el programa.
```

## Decisiones técnicas

- **Reintentos centralizados:** la lógica vive en `BaseLLMClient`. Los reintentos internos de los SDKs se desactivan (`max_retries=0`) para que no se multipliquen.
- **Errores temporales y permanentes:** límite de tasa (429), errores de conexión, errores 5xx y tiempos agotados se reintentan con backoff exponencial (1, 2, 4 s, con variación aleatoria). Los demás errores, como una clave inválida, se devuelven de inmediato como `ModelResponse` con el campo `error`.
- **Tiempo límite:** cada llamada se envuelve en `asyncio.timeout()`.
- **Streaming:** solo se reintenta si todavía no llegó ningún fragmento, para no duplicar texto.
- **Mensajes `system` en Anthropic:** se extraen de la conversación y se envían en el parámetro `system`, como exige su API.
- **Temperatura en Anthropic:** la versión 2.x del SDK de Anthropic ya no acepta el parámetro `temperature`, por lo que este cliente no lo envía. El valor se sigue validando con Pydantic y lo usa el cliente de OpenAI.
- **Variables genéricas:** los nombres `OPENAI_*` y `ANTHROPIC_*` describen el SDK, no el proveedor, para que el cambio a los servicios originales sea solo de configuración.

## Limitaciones conocidas

- El modelo local `qwen2.5:1.5b` es pequeño y corre sin GPU: responde más lento y con menos precisión que un modelo en la nube.
- El manejo del error 429 (límite de tasa) está implementado, pero no se provocó en las pruebas para no agotar la cuota gratuita de Gemini. El mecanismo de reintento se verificó con errores de conexión, que siguen el mismo camino.
- Los límites gratuitos de Gemini dependen del proyecto de Google Cloud y pueden cambiar.

## Estructura

```
pre-entrega-01/
├── README.md
├── requirements.txt
├── .env.example
├── schemas.py
├── base_client.py
├── openai_client.py
├── anthropic_client.py
├── manager.py
└── main.py