"""Crea el índice serverless de Pinecone si no existe y verifica su dimensión."""
import logging
import time

from dotenv import load_dotenv
from pinecone import ServerlessSpec

from config import (
    METRICA,
    PINECONE_CLOUD,
    PINECONE_REGION,
    Settings,
    crear_cliente_pinecone,
    crear_embeddings,
)

logger = logging.getLogger("setup")


def _esta_listo(descripcion) -> bool:
    estado = getattr(descripcion, "status", None)
    if isinstance(estado, dict):
        return bool(estado.get("ready"))
    return bool(getattr(estado, "ready", False))


def asegurar_indice() -> None:
    settings = Settings.desde_entorno()
    pc = crear_cliente_pinecone(settings)

    # Medimos la dimensión real del modelo en lugar de suponerla.
    dimension = len(crear_embeddings(settings).embed_query("prueba de dimensión"))
    logger.info("El modelo %s genera vectores de %d dimensiones",
                settings.embedding_model, dimension)

    if pc.has_index(settings.index_name):
        actual = pc.describe_index(settings.index_name).dimension
        if actual != dimension:
            raise RuntimeError(
                f"El índice '{settings.index_name}' tiene dimensión {actual}, pero el modelo "
                f"genera {dimension}. Usa otro INDEX_NAME o elimina el índice."
            )
        logger.info("El índice '%s' ya existe con la dimensión correcta: no se crea de nuevo",
                    settings.index_name)
        return

    logger.info("Creando índice serverless '%s' (%s %s, métrica %s)",
                settings.index_name, PINECONE_CLOUD, PINECONE_REGION, METRICA)
    pc.create_index(
        name=settings.index_name,
        dimension=dimension,
        metric=METRICA,
        spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
    )
    for _ in range(60):
        if _esta_listo(pc.describe_index(settings.index_name)):
            logger.info("Índice '%s' listo", settings.index_name)
            return
        time.sleep(2)
    raise TimeoutError("El índice no estuvo listo después de 2 minutos")


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    asegurar_indice()