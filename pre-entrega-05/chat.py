"""Chat interactivo con memoria persistente: python chat.py --thread mi-sesion"""
import argparse
import asyncio
import logging

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent import construir_grafo, ejecutar_turno
from config import BASE_DIR

DB_CHAT = BASE_DIR / "checkpoints.sqlite"


async def main(thread_id: str) -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(f"Sesión '{thread_id}'. Escribe 'salir' para terminar.\n")
    async with AsyncSqliteSaver.from_conn_string(str(DB_CHAT)) as checkpointer:
        grafo = construir_grafo(checkpointer)
        while (mensaje := input("Tú: ").strip()).lower() != "salir":
            if mensaje:
                respuesta, _ = await ejecutar_turno(grafo, thread_id, mensaje)
                print(f"Agente: {respuesta}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chat con el agente de pedidos.")
    parser.add_argument("--thread", default="sesion-interactiva", help="Identificador de la sesión.")
    asyncio.run(main(parser.parse_args().thread))