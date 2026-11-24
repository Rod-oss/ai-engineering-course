"""Cliente para APIs compatibles con OpenAI (configurado con Gemini)."""
from collections.abc import AsyncIterator

import openai
from openai import AsyncOpenAI

from base_client import BaseLLMClient, LLMClientError
from schemas import ChatMessage, ModelConfig, ModelResponse, ProviderSettings
from base_client import BaseLLMClient, LLMClientError, api_error_message



class OpenAIClient(BaseLLMClient):
    """Traduce el SDK de OpenAI a la interfaz común."""

    provider_name = "openai"

    def __init__(self, settings: ProviderSettings, config: ModelConfig) -> None:
        super().__init__(settings, config)
        self._client = AsyncOpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.base_url,
            timeout=config.timeout,
            max_retries=0,  # los reintentos los gestiona BaseLLMClient
        )

    def _request(self, messages: list[ChatMessage]) -> dict:
        return {
            "model": self.config.model,
            "messages": [m.model_dump() for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

    async def _generate(self, messages: list[ChatMessage]) -> ModelResponse:
        response = await self._client.chat.completions.create(**self._request(messages))
        choice = response.choices[0]
        usage = response.usage
        return ModelResponse(
            provider=self.provider_name,
            model=response.model or self.config.model,
            content=choice.message.content or "",
            finish_reason=choice.finish_reason,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    async def _stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            **self._request(messages), stream=True
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _classify_error(self, exc: Exception) -> LLMClientError:
        if isinstance(exc, openai.RateLimitError):
            return LLMClientError("Límite de tasa alcanzado (429)", retryable=True)
        if isinstance(exc, openai.APIConnectionError):
            return LLMClientError(f"Error de conexión: {exc}", retryable=True)
        if isinstance(exc, openai.InternalServerError):
            return LLMClientError(f"Error del servidor ({exc.status_code})", retryable=True)
        if isinstance(exc, openai.APIStatusError):
                     return LLMClientError(f"Error de la API ({exc.status_code}): {api_error_message(exc)}", retryable=False)
        return LLMClientError(f"Error inesperado: {exc!r}", retryable=False)