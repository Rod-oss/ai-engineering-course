"""Esquemas de datos validados con Pydantic."""
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class ChatMessage(BaseModel):
    """Un mensaje de la conversación."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ModelConfig(BaseModel):
    """Parámetros de generación, con rangos validados."""

    model: str = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=400, gt=0, le=8192)
    timeout: float = Field(default=30.0, gt=0, description="Segundos máximos por llamada")
    max_retries: int = Field(default=3, ge=0, le=5)


class ProviderSettings(BaseModel):
    """Credenciales y dirección del proveedor. La clave nunca se imprime."""

    api_key: SecretStr = Field(min_length=1)
    base_url: str | None = None


class ModelResponse(BaseModel):
    """Respuesta unificada, con la misma forma para todos los proveedores."""

    provider: str
    model: str
    content: str = ""
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None