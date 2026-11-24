"""AsyncLLMManager: crea el cliente adecuado según la configuración (patrón Factory)."""
import os
from collections.abc import AsyncIterator

from anthropic_client import AnthropicClient
from base_client import BaseLLMClient
from openai_client import OpenAIClient
from schemas import ChatMessage, ModelConfig, ModelResponse, ProviderSettings

PROVIDERS: dict[str, type[BaseLLMClient]] = {
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
}


class AsyncLLMManager:
    """Punto de entrada único: el resto del programa nunca elige el SDK."""

    def __init__(
        self,
        provider: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        **config_overrides,
    ) -> None:
        name = (provider or os.getenv("LLM_PROVIDER", "openai")).strip().lower()
        if name not in PROVIDERS:
            raise ValueError(f"Proveedor desconocido: '{name}'. Opciones: {', '.join(PROVIDERS)}")

        prefix = name.upper()
        settings = ProviderSettings(
            api_key=api_key or os.getenv(f"{prefix}_API_KEY", ""),
            base_url=base_url or os.getenv(f"{prefix}_BASE_URL") or None,
        )
        config_values = {
            "model": os.getenv(f"{prefix}_MODEL", ""),
            "timeout": os.getenv(f"{prefix}_TIMEOUT", "30"),
        }
        config_values.update(config_overrides)

        self.provider = name
        self.client: BaseLLMClient = PROVIDERS[name](settings, ModelConfig(**config_values))

    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        return await self.client.generate(messages)

    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        return self.client.stream(messages)