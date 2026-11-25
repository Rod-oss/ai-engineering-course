"""Capa de modelos: LLM de chat y embeddings, ambos con interfaz asíncrona."""

from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import OpenAIEmbeddings

from app.settings import Settings


def crear_llm(settings: Settings) -> BaseChatModel:
    """Crea el único modelo de chat del proceso.

    El limitador controla el ritmo ANTES de llamar al proveedor (por ejemplo, 12 llamadas por
    minuto frente al límite de 15 del nivel gratuito de Gemini). Como todos los agentes comparten
    esta instancia, también comparten el limitador.
    """
    limitador = InMemoryRateLimiter(
        requests_per_second=settings.llm_rpm / 60, check_every_n_seconds=0.1, max_bucket_size=1
    )
    comunes = {"timeout": settings.llm_timeout_s, "max_retries": settings.llm_max_retries, "rate_limiter": limitador}
    if settings.llm_provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=settings.llm_model, google_api_key=settings.llm_api_key, **comunes)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.llm_model, api_key=settings.llm_api_key, **comunes)


def crear_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """Embeddings vía endpoint compatible con OpenAI (Gemini). Se usan con aembed_query (asíncrono)."""
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        check_embedding_ctx_length=False,  # envía texto, no tokens de OpenAI
        max_retries=3,
    )
