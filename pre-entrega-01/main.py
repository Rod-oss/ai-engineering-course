"""Script de validación de la Pre-entrega 1: Unified Async LLM Client."""
import asyncio
import logging
import os

from dotenv import load_dotenv
from pydantic import ValidationError

from manager import AsyncLLMManager
from schemas import ChatMessage

MENSAJES = [
    ChatMessage(role="system", content="Responde en español, en un máximo de tres oraciones."),
    ChatMessage(role="user", content="¿Qué es la entropía?"),
]


def titulo(texto: str) -> None:
    print(f"\n{'=' * 70}\n{texto}\n{'=' * 70}")


async def probar_proveedor(provider: str) -> None:
    manager = AsyncLLMManager(provider=provider)
    cliente = type(manager.client).__name__
    titulo(f"Proveedor: {provider} | Cliente: {cliente} | Modelo: {manager.client.config.model}")

    print("\n[Modo normal]")
    respuesta = await manager.generate(MENSAJES)
    if respuesta.ok:
        print(respuesta.content)
        print(
            f"(tokens: {respuesta.input_tokens} de entrada, {respuesta.output_tokens} de salida"
            f" | fin: {respuesta.finish_reason})"
        )
    else:
        print(f"Error controlado: {respuesta.error}")

    print("\n[Modo streaming]")
    async for fragmento in manager.stream(MENSAJES):
        print(fragmento, end="", flush=True)
    print()


async def probar_resiliencia() -> None:
    titulo("Pruebas de validación y resiliencia")

    print("\n1. Pydantic rechaza una temperatura fuera de rango (3.0):")
    try:
        AsyncLLMManager(provider="openai", temperature=3.0)
    except ValidationError as err:
        print(f"   Rechazada: {err.errors()[0]['msg']}")

    print("\n2. Clave inválida (error permanente, no se reintenta):")
    manager = AsyncLLMManager(provider="openai", api_key="clave-invalida")
    respuesta = await manager.generate(MENSAJES)
    print(f"   {respuesta.error}")

    print("\n3. Servidor inaccesible (error temporal, se reintenta con backoff):")
    manager = AsyncLLMManager(provider="anthropic", base_url="http://127.0.0.1:9999", max_retries=2)
    respuesta = await manager.generate(MENSAJES)
    print(f"   {respuesta.error}")


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="   %(levelname)s %(message)s")

    por_defecto = os.getenv("LLM_PROVIDER", "openai")
    manager = AsyncLLMManager()  # sin argumentos: decide según LLM_PROVIDER
    titulo(f"LLM_PROVIDER={por_defecto} -> AsyncLLMManager() creó {type(manager.client).__name__}")

    for provider in ("openai", "anthropic"):
        await probar_proveedor(provider)

    await probar_resiliencia()
    print("\nValidación terminada: ningún error detuvo el programa.")


if __name__ == "__main__":
    asyncio.run(main())