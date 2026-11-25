"""Configuración compartida: embeddings, base vectorial y LLM se crean en un solo lugar."""
import os
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field, SecretStr

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VECTORSTORE_DIR = BASE_DIR / "vectorstore"
COLLECTION_NAME = "kestrel_docs"

CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
TOP_K = 4


class Settings(BaseModel):
    """Configuración validada, leída de las variables de entorno."""

    api_key: SecretStr = Field(min_length=1)
    base_url: str | None = None
    chat_model: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    timeout: float = Field(default=30.0, gt=0)

    @classmethod
    def desde_entorno(cls) -> "Settings":
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            chat_model=os.getenv("OPENAI_MODEL", ""),
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", ""),
            timeout=os.getenv("OPENAI_TIMEOUT", "30"),
        )


def crear_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """Única fuente del modelo de embeddings: la usan la ingesta y la consulta."""
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        # Envía el texto tal cual, no tokens de OpenAI: necesario para proveedores como Gemini.
        check_embedding_ctx_length=False,
        timeout=settings.timeout,
        max_retries=3,
    )


def crear_vectorstore(settings: Settings) -> Chroma:
    """Abre (o crea) la colección persistente en ./vectorstore."""
    cliente = chromadb.PersistentClient(
        path=str(VECTORSTORE_DIR),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return Chroma(
        client=cliente,
        collection_name=COLLECTION_NAME,
        embedding_function=crear_embeddings(settings),
        # Guardamos qué modelo indexó la colección para detectar embeddings no coincidentes.
        collection_metadata={"embedding_model": settings.embedding_model},
    )


def crear_llm(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=0,
        timeout=settings.timeout,
        max_retries=2,
    )