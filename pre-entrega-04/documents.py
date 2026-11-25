"""Carga y fragmentación de documentos. La usan la ingesta (Pinecone) y BM25."""
import json
import re

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS, DATA_DIR

CODIFICACION = "cl100k_base"  # contador de tokens de OpenAI, usado como aproximación


def cargar_catalogo() -> dict:
    return json.loads((DATA_DIR / "catalogo.json").read_text(encoding="utf-8"))


def cargar_fragmentos() -> list[Document]:
    """Fragmenta cada documento y le agrega metadatos de fuente, sección y categoría."""
    catalogo = cargar_catalogo()
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=CODIFICACION,
        chunk_size=CHUNK_SIZE_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        separators=["\n## ", "\n\n", "\n", ". ", " ", ""],
    )
    codificador = tiktoken.get_encoding(CODIFICACION)

    fragmentos: list[Document] = []
    for archivo in sorted(DATA_DIR.glob("*.md")):
        if archivo.name not in catalogo:
            raise ValueError(f"{archivo.name} no tiene categoría en data/catalogo.json")
        info = catalogo[archivo.name]
        texto = archivo.read_text(encoding="utf-8").strip()
        titulo = texto.splitlines()[0].lstrip("# ").strip()

        for indice, parte in enumerate(splitter.split_text(texto)):
            chunk_id = f"{archivo.stem}-{indice:02d}"
            fragmentos.append(
                Document(
                    id=chunk_id,
                    page_content=parte,
                    metadata={
                        "chunk_id": chunk_id,
                        "source": archivo.name,
                        "titulo": titulo,
                        "categoria": info["categoria"],
                        "etiquetas": info["etiquetas"],
                        "secciones": re.findall(r"^##\s+(.+)$", parte, flags=re.MULTILINE),
                        "chunk": indice,
                        "tokens": len(codificador.encode(parte)),
                    },
                )
            )
    return fragmentos