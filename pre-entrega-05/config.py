"""Configuración validada del agente y fábrica del LLM."""
import os
from pathlib import Path
from typing import Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field, SecretStr

BASE_DIR = Path(__file__).resolve().parent
RECURSION_LIMIT = 10          # techo de pasos por turno, para evitar bucles y costos
MAX_TOKENS_HISTORIAL = 4000   # el historial enviado al modelo se recorta a este tamaño


class Settings(BaseModel):
    provider: Literal["google", "openai"] = "google"
    api_key: SecretStr = Field(min_length=1)
    model: str = Field(min_length=1)
    timeout: float = Field(default=60.0, gt=0)

    @classmethod
    def desde_entorno(cls) -> "Settings":
        provider = os.getenv("LLM_PROVIDER", "google").strip().lower()
        variable_clave = "GOOGLE_API_KEY" if provider == "google" else "OPENAI_API_KEY"
        return cls(
            provider=provider,
            api_key=os.getenv(variable_clave, ""),
            model=os.getenv("LLM_MODEL", ""),
            timeout=os.getenv("LLM_TIMEOUT", "60"),
        )


def crear_llm(settings: Settings) -> BaseChatModel:
    """Crea el modelo de chat según el proveedor configurado."""
    if settings.provider == "google":
        # Integración nativa: conserva las thought signatures que Gemini 3 exige con herramientas.
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.model,
            google_api_key=settings.api_key,
            timeout=settings.timeout,
            max_retries=3,
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        timeout=settings.timeout,
        max_retries=3,
    )