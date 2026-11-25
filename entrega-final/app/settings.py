"""Configuración centralizada y validada con Pydantic.

Todo sale de variables de entorno (o del archivo .env). Nada de modelos, índices ni claves
escritos en el código: si falta un valor obligatorio, la aplicación no arranca y el error
indica exactamente qué variable falta.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # LLM de los agentes
    llm_provider: Literal["google", "openai"] = "google"
    llm_model: str = Field(min_length=1)
    llm_api_key: SecretStr = Field(
        min_length=1, validation_alias=AliasChoices("LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    llm_rpm: int = Field(default=12, ge=1, description="Máximo de llamadas por minuto al LLM (limitador compartido).")
    llm_timeout_s: float = Field(default=90, gt=0)
    llm_max_retries: int = Field(default=6, ge=0)

    # Embeddings (los mismos con los que se indexó Pinecone)
    embedding_model: str = Field(
        min_length=1, validation_alias=AliasChoices("EMBEDDING_MODEL", "OPENAI_EMBEDDING_MODEL")
    )
    embedding_api_key: SecretStr = Field(
        min_length=1, validation_alias=AliasChoices("EMBEDDING_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY")
    )
    embedding_base_url: str | None = Field(
        default=None, validation_alias=AliasChoices("EMBEDDING_BASE_URL", "OPENAI_BASE_URL")
    )

    # Pinecone
    pinecone_api_key: SecretStr = Field(min_length=1)
    pinecone_index: str = Field(
        pattern=r"^[a-z0-9-]{1,45}$", validation_alias=AliasChoices("PINECONE_INDEX", "INDEX_NAME")
    )
    pinecone_namespace: str = Field(min_length=1)

    # Recuperación híbrida
    data_dir: Path = BASE_DIR / "data"
    rag_top_k: int = Field(default=4, ge=1, le=20)
    rag_peso_vectorial: float = Field(
        default=0.5, ge=0, le=1, description="Peso de la búsqueda semántica en la fusión RRF."
    )
    rag_rrf_k: int = Field(default=60, ge=1, description="Constante de Reciprocal Rank Fusion.")

    # Agentes
    max_pasos_supervisor: int = Field(default=6, ge=1)
    recursion_limit_especialista: int = Field(default=8, ge=2)
    recursion_limit_grafo: int = Field(default=25, ge=5)

    # Servicio
    redis_url: str = "redis://localhost:6379"
    worker_concurrency: int = Field(default=2, ge=1)
    job_ttl_dias: int = Field(default=7, ge=1)

    # Observabilidad
    phoenix_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project: str = "kestrel-intelligence"


@lru_cache
def get_settings() -> Settings:
    return Settings()
