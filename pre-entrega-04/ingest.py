"""Ingesta: fragmenta los documentos y los sube a Pinecone con texto y metadatos."""
import argparse
import logging
import time
from collections import Counter

from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore

from config import NAMESPACE, Settings, crear_cliente_pinecone, crear_embeddings
from documents import cargar_fragmentos

logger = logging.getLogger("ingesta")


def contar_vectores(index) -> int:
    stats = index.describe_index_stats()
    datos = stats.to_dict() if hasattr(stats, "to_dict") else dict(stats)
    return int((datos.get("namespaces") or {}).get(NAMESPACE, {}).get("vector_count", 0))


def ingestar(reconstruir: bool = False) -> None:
    settings = Settings.desde_entorno()
    pc = crear_cliente_pinecone(settings)
    if not pc.has_index(settings.index_name):
        raise RuntimeError("El índice no existe. Ejecuta primero: python setup_index.py")
    index = pc.Index(settings.index_name)

    existentes = contar_vectores(index)
    if existentes and not reconstruir:
        logger.info("El namespace '%s' ya tiene %d vectores: se omite la ingesta "
                    "(usa --rebuild para rehacerla)", NAMESPACE, existentes)
        return
    if existentes and reconstruir:
        index.delete(delete_all=True, namespace=NAMESPACE)
        logger.info("Namespace '%s' vaciado para reconstruirlo", NAMESPACE)

    fragmentos = cargar_fragmentos()
    for fuente, cantidad in sorted(Counter(f.metadata["source"] for f in fragmentos).items()):
        logger.info("  %-16s %d fragmento(s)", fuente, cantidad)
    tokens = [f.metadata["tokens"] for f in fragmentos]
    logger.info("%d fragmentos (tokens: mín. %d, máx. %d, promedio %d)",
                len(fragmentos), min(tokens), max(tokens), sum(tokens) // len(tokens))

    vectorstore = PineconeVectorStore(
        index=index, embedding=crear_embeddings(settings), namespace=NAMESPACE, text_key="text"
    )
    vectorstore.add_documents(fragmentos, ids=[f.metadata["chunk_id"] for f in fragmentos])

    # Pinecone confirma las escrituras con unos segundos de retraso.
    for _ in range(30):
        total = contar_vectores(index)
        if total >= len(fragmentos):
            logger.info("%d vectores disponibles en el namespace '%s'", total, NAMESPACE)
            return
        time.sleep(2)
    logger.warning("Pinecone todavía no reporta todos los vectores; espera unos segundos")


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser(description="Sube los documentos de /data a Pinecone.")
    parser.add_argument("--rebuild", action="store_true", help="Vacía el namespace y reindexa.")
    ingestar(reconstruir=parser.parse_args().rebuild)