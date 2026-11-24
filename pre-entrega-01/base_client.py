"""Clase base abstracta: el contrato común de todos los clientes de LLM."""
import asyncio
import logging
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

from schemas import ChatMessage, ModelConfig, ModelResponse, ProviderSettings

logger = logging.getLogger(__name__)
T = TypeVar("T")


class LLMClientError(Exception):
    """Error controlado. `retryable` indica si tiene sentido reintentar."""

    def __init__(self, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable

def api_error_message(exc: Exception) -> str:
    """Extrae el mensaje legible que el proveedor envía en el cuerpo del error."""
    body = getattr(exc, "body", None)
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        detail = body.get("error", body)
        if isinstance(detail, dict) and detail.get("message"):
            return str(detail["message"])
    return str(getattr(exc, "message", exc))

class BaseLLMClient(ABC):
    """Define la interfaz común y la lógica de reintentos compartida."""

    provider_name: str = "base"

    def __init__(self, settings: ProviderSettings, config: ModelConfig) -> None:
        self.settings = settings
        self.config = config

    # ---------- Métodos que cada proveedor debe implementar ----------

    @abstractmethod
    async def _generate(self, messages: list[ChatMessage]) -> ModelResponse:
        """Llamada directa al SDK del proveedor, sin reintentos."""

    @abstractmethod
    def _stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Generador asíncrono que entrega fragmentos de texto del SDK."""

    @abstractmethod
    def _classify_error(self, exc: Exception) -> LLMClientError:
        """Traduce una excepción del SDK a un LLMClientError."""

    # ---------- Interfaz pública: igual para todos los proveedores ----------

    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        """Devuelve la respuesta completa. Nunca deja escapar errores del proveedor."""
        try:
            return await self._with_retries(lambda: self._generate(messages))
        except LLMClientError as err:
            return ModelResponse(
                provider=self.provider_name, model=self.config.model, error=str(err)
            )

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Entrega la respuesta por fragmentos. Reintenta solo si aún no llegó texto."""
        for attempt in range(self.config.max_retries + 1):
            received_text = False
            try:
                async for fragment in self._stream(messages):
                    received_text = True
                    yield fragment
                return
            except Exception as exc:
                err = self._to_client_error(exc)
                if received_text or not err.retryable or attempt == self.config.max_retries:
                    yield f"\n[Error controlado] {err}"
                    return
                await self._wait_before_retry(attempt, err)

    # ---------- Lógica interna compartida ----------

    async def _with_retries(self, operation: Callable[[], Awaitable[T]]) -> T:
        for attempt in range(self.config.max_retries + 1):
            try:
                async with asyncio.timeout(self.config.timeout):
                    return await operation()
            except Exception as exc:
                err = self._to_client_error(exc)
                if not err.retryable or attempt == self.config.max_retries:
                    raise err from exc
                await self._wait_before_retry(attempt, err)
        raise LLMClientError("No quedan intentos disponibles", retryable=False)

    def _to_client_error(self, exc: Exception) -> LLMClientError:
        if isinstance(exc, LLMClientError):
            return exc
        if isinstance(exc, TimeoutError):
            return LLMClientError(
                f"Tiempo de espera agotado ({self.config.timeout:.0f} s)", retryable=True
            )
        return self._classify_error(exc)

    async def _wait_before_retry(self, attempt: int, err: LLMClientError) -> None:
        delay = 2**attempt + random.uniform(0, 0.5)  # backoff exponencial: 1, 2, 4 s...
        logger.warning(
            "[%s] %s. Reintento %d de %d en %.1f s",
            self.provider_name, err, attempt + 1, self.config.max_retries, delay,
        )
        await asyncio.sleep(delay)