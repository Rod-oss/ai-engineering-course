"""Ingesta: lee /data, fragmenta por tokens y persiste los fragmentos en ChromaDB."""
import argparse
import hashlib
import logging
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    DATA_DIR,
    VECTORSTORE_DIR,
    Settings,
    crear_vectorstore,
)

logger = logging.getLogger("ingesta")
CODIFICACION = "cl100k_base"  # contador de tokens de OpenAI, usado como aproximación


def cargar_documentos(carpeta: Path) -> list[Document]:
    archivos = sorted([*carpeta.glob("*.md"), *carpeta.glob("*.txt")])
    if not archivos:
        raise FileNotFoundError(f"No hay archivos .md o .txt en {carpeta}")
    documentos = []
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8").strip()
        if texto:
            documentos.append(Document(page_content=texto, metadata={"source": archivo.name}))
            logger.info("Cargado %s (%d caracteres)", archivo.name, len(texto))
    return documentos


def fragmentar(documentos: list[Document]) -> list[Document]:
    """Divide por tokens, respetando primero las secciones de Markdown y luego los párrafos."""
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=CODIFICACION,
        chunk_size=CHUNK_SIZE_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        separators=["\n## ", "\n\n", "\n", ". ", " ", ""],
    )
    fragmentos = splitter.split_documents(documentos)
    contador: dict[str, int] = {}
    for fragmento in fragmentos:
        fuente = fragmento.metadata["source"]
        indice = contador.get(fuente, 0)
        contador[fuente] = indice + 1
        fragmento.metadata["chunk"] = indice
        fragmento.metadata["ref"] = f"{fuente}#{indice}"
    return fragmentos


def id_estable(fragmento: Document) -> str:
    """Mismo contenido, mismo ID: reindexar no duplica fragmentos."""
    clave = f"{fragmento.metadata['ref']}|{fragmento.page_content}"
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()[:32]


def ingestar(reconstruir: bool = False) -> int:
    settings = Settings.desde_entorno()
    vectorstore = crear_vectorstore(settings)
    existentes = vectorstore._collection.count()

    if existentes and not reconstruir:
        logger.info("La colección ya tiene %d fragmentos: se omite la ingesta "
                    "(usa --rebuild para rehacerla)", existentes)
        return existentes
    if existentes and reconstruir:
        vectorstore.reset_collection()
        logger.info("Colección vaciada para reconstruirla")

    fragmentos = fragmentar(cargar_documentos(DATA_DIR))
    codificador = tiktoken.get_encoding(CODIFICACION)
    tamanos = [len(codificador.encode(f.page_content)) for f in fragmentos]
    logger.info("%d fragmentos (tokens por fragmento: mín. %d, máx. %d, promedio %d)",
                len(fragmentos), min(tamanos), max(tamanos), sum(tamanos) // len(tamanos))

    vectorstore.add_documents(fragmentos, ids=[id_estable(f) for f in fragmentos])
    logger.info("Guardados en %s con el modelo de embeddings %s",
                VECTORSTORE_DIR, settings.embedding_model)
    return len(fragmentos)


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser(description="Indexa los documentos de /data en ChromaDB.")
    parser.add_argument("--rebuild", action="store_true", help="Vacía la colección y reindexa todo.")
    ingestar(reconstruir=parser.parse_args().rebuild)