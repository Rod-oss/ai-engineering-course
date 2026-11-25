"""Crea el índice de Pinecone y carga la documentación, de forma asíncrona.

    python scripts/ingestar.py              # omite la carga si el namespace ya tiene vectores
    python scripts/ingestar.py --rebuild    # vacía el namespace y vuelve a cargar

Solo hace falta en una instalación nueva: el índice de la Pre-entrega 4 ya sirve.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pinecone import PineconeAsyncio, ServerlessSpec  # noqa: E402

from app.llm import crear_embeddings  # noqa: E402
from app.rag.documentos import cargar_fragmentos  # noqa: E402
from app.settings import get_settings  # noqa: E402

DIMENSION = 3072  # gemini-embedding-001
LOTE = 50


async def contar(indice, namespace: str) -> int:
    stats = (await indice.describe_index_stats()).to_dict()
    return int((stats.get("namespaces") or {}).get(namespace, {}).get("vector_count", 0))


async def main(reconstruir: bool) -> None:
    settings = get_settings()
    async with PineconeAsyncio(api_key=settings.pinecone_api_key.get_secret_value()) as cliente:
        if not await cliente.has_index(settings.pinecone_index):
            print(f"Creando el índice '{settings.pinecone_index}'...")
            await cliente.create_index(
                name=settings.pinecone_index,
                dimension=DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        host = (await cliente.describe_index(settings.pinecone_index)).host
        async with cliente.IndexAsyncio(host=host) as indice:
            existentes = await contar(indice, settings.pinecone_namespace)
            if existentes and not reconstruir:
                print(f"El namespace ya tiene {existentes} vectores; no se carga nada (usa --rebuild para rehacerlo).")
                return
            if existentes:
                await indice.delete(delete_all=True, namespace=settings.pinecone_namespace)

            fragmentos = await asyncio.to_thread(cargar_fragmentos, settings.data_dir)
            vectores = await crear_embeddings(settings).aembed_documents([f.page_content for f in fragmentos])
            registros = [
                {
                    "id": f.metadata["chunk_id"],
                    "values": v,
                    "metadata": {
                        "text": f.page_content,
                        **{k: f.metadata[k] for k in ("chunk_id", "source", "titulo", "categoria", "etiquetas")},
                    },
                }
                for f, v in zip(fragmentos, vectores, strict=True)
            ]
            for i in range(0, len(registros), LOTE):
                await indice.upsert(vectors=registros[i : i + LOTE], namespace=settings.pinecone_namespace)
            print(f"{len(registros)} fragmentos cargados en '{settings.pinecone_index}/{settings.pinecone_namespace}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingesta de la documentación en Pinecone")
    parser.add_argument("--rebuild", action="store_true")
    asyncio.run(main(parser.parse_args().rebuild))
