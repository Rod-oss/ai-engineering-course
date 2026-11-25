"""Configuración compartida: embeddings, cliente de Pinecone y constantes del sistema."""
import os
from pathlib import Path

from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone
from pydantic import BaseModel, Field, SecretStr

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

NAMESPACE = "kestrel-docs"
PINECONE_CLOUD = "aws"
PINECONE_REGION = "us-east-1"  # región obligatoria en el plan gratuito Starter
METRICA = "cosine"

CHUNK_SIZE_TOKENS = 600
CHUNK_OVERLAP_TOKENS = 60
TOP_K = 5


class Settings(BaseModel):
    """Configuración validada, leída de las variables de entorno."""

    openai_api_key: SecretStr = Field(min_length=1)
    openai_base_url: str | None = None
    embedding_model: str = Field(min_length=1)
    pinecone_api_key: SecretStr = Field(min_length=1)
    index_name: str = Field(pattern=r"^[a-z0-9-]{1,45}$")
    timeout: float = Field(default=30.0, gt=0)

    @classmethod
    def desde_entorno(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", ""),
            pinecone_api_key=os.getenv("PINECONE_API_KEY", ""),
            index_name=os.getenv("INDEX_NAME", ""),
            timeout=os.getenv("OPENAI_TIMEOUT", "30"),
        )


def crear_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """Única fuente del modelo de embeddings: la usan el setup, la ingesta y la búsqueda."""
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        check_embedding_ctx_length=False,  # envía texto, no tokens de OpenAI
        timeout=settings.timeout,
        max_retries=3,
    )


def crear_cliente_pinecone(settings: Settings) -> Pinecone:
    return Pinecone(api_key=settings.pinecone_api_key.get_secret_value())