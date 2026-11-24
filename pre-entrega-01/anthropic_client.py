"""Cliente para APIs compatibles con Anthropic (configurado con Ollama)."""
from collections.abc import AsyncIterator

import anthropic
from anthropic import AsyncAnthropic

from base_client import BaseLLMClient, LLMClientError
from schemas import ChatMessage, ModelConfig, ModelResponse, ProviderSettings


class AnthropicClient(BaseLLMClient):
    """Traduce el SDK de Anthropic a la interfaz común."""

    provider_name = "anthropic"

    def __init__(self, settings: ProviderSettings, config: ModelConfig) -> None:
        super().__init__(settings, config)
        self._client = AsyncAnthropic(
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.base_url,
            timeout=config.timeout,
            max_retries=0,  # los reintentos los gestiona BaseLLMClient
        )

    def _request(self, messages: list[ChatMessage]) -> dict:
        # Anthropic no acepta el rol "system" en la conversación: va en un parámetro aparte.
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        request = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,  # obligatorio en Anthropic
            # El SDK de Anthropic 2.x ya no acepta `temperature`, así que no se envía.
            "messages": [m.model_dump() for m in messages if m.role != "system"],
        }
        if system:
            request["system"] = system
        return request

    async def _generate(self, messages: list[ChatMessage]) -> ModelResponse:
        response = await self._client.messages.create(**self._request(messages))
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = getattr(response, "usage", None)
        return ModelResponse(
            provider=self.provider_name,
            model=response.model or self.config.model,
            content=text,
            finish_reason=response.stop_reason,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )

    async def _stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        async with self._client.messages.stream(**self._request(messages)) as stream:
            async for text in stream.text_stream:
                yield text

    def _classify_error(self, exc: Exception) -> LLMClientError:
        if isinstance(exc, anthropic.RateLimitError):
            return LLMClientError("Límite de tasa alcanzado (429)", retryable=True)
        if isinstance(exc, anthropic.APIConnectionError):
            return LLMClientError(f"Error de conexión: {exc}", retryable=True)
        if isinstance(exc, anthropic.InternalServerError):
            return LLMClientError(f"Error del servidor ({exc.status_code})", retryable=True)
        if isinstance(exc, anthropic.APIStatusError):
            return LLMClientError(f"Error de la API ({exc.status_code}): {exc.message}", retryable=False)
        return LLMClientError(f"Error inesperado: {exc!r}", retryable=False)