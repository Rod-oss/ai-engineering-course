"""Configuración del servicio: LLM, base vectorial, Redis, worker y observabilidad."""
import os
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from pydantic import BaseModel, Field, SecretStr
from langchain_core.rate_limiters import InMemoryRateLimiter

MAX_PASOS_SUPERVISOR = 6
RECURSION_LIMIT_ESPECIALISTA = 8
RECURSION_LIMIT_GRAFO = 25
TOP_K = 4

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "2"))
PHOENIX_ENDPOINT = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")
PHOENIX_PROJECT = os.getenv("PHOENIX_PROJECT", "kestrel-orquestador")
LLM_RPM = int(os.getenv("LLM_RPM", "12"))
# Un único limitador compartido por todos los modelos del proceso,
# para no superar el límite por minuto del proveedor (15 RPM en Gemini gratuito).
LIMITADOR_LLM = InMemoryRateLimiter(
    requests_per_second=LLM_RPM / 60,
    check_every_n_seconds=0.1,
    max_bucket_size=1,
)


class Settings(BaseModel):
    provider: Literal["google", "openai"] = "google"
    llm_api_key: SecretStr = Field(min_length=1)
    llm_model: str = Field(min_length=1)
    embedding_api_key: SecretStr = Field(min_length=1)
    embedding_base_url: str | None = None
    embedding_model: str = Field(min_length=1)
    pinecone_api_key: SecretStr = Field(min_length=1)
    index_name: str = Field(pattern=r"^[a-z0-9-]{1,45}$")
    namespace: str = Field(min_length=1)

    @classmethod
    def desde_entorno(cls) -> "Settings":
        provider = os.getenv("LLM_PROVIDER", "google").strip().lower()
        return cls(
            provider=provider,
            llm_api_key=os.getenv("GOOGLE_API_KEY" if provider == "google" else "OPENAI_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            embedding_api_key=os.getenv("OPENAI_API_KEY", ""),
            embedding_base_url=os.getenv("OPENAI_BASE_URL") or None,
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", ""),
            pinecone_api_key=os.getenv("PINECONE_API_KEY", ""),
            index_name=os.getenv("INDEX_NAME", ""),
            namespace=os.getenv("PINECONE_NAMESPACE", "kestrel-docs"),
        )


def crear_llm(settings: Settings) -> BaseChatModel:
    if settings.provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=settings.llm_model, google_api_key=settings.llm_api_key,
                                      timeout=90, rate_limiter=LIMITADOR_LLM, max_retries=6)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.llm_model, api_key=settings.llm_api_key, timeout=90, rate_limiter=LIMITADOR_LLM, max_retries=6)


def crear_vectorstore(settings: Settings) -> PineconeVectorStore:
    pc = Pinecone(api_key=settings.pinecone_api_key.get_secret_value())
    if not pc.has_index(settings.index_name):
        raise RuntimeError(f"No existe el índice '{settings.index_name}'. Créalo con la Pre-entrega 4.")
    embeddings = OpenAIEmbeddings(model=settings.embedding_model, api_key=settings.embedding_api_key,
                                  base_url=settings.embedding_base_url, check_embedding_ctx_length=False)
    return PineconeVectorStore(index=pc.Index(settings.index_name), embedding=embeddings,
                               namespace=settings.namespace, text_key="text")