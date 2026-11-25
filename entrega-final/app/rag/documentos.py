"""Carga y fragmentación de la documentación (misma configuración que la ingesta de la Pre-entrega 4).

La usan la ingesta a Pinecone (scripts/ingestar.py) y el índice BM25, así que ambos buscadores
trabajan exactamente con los mismos fragmentos e identificadores.
"""

import json
import re
from pathlib import Path

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

CODIFICACION = "cl100k_base"
CHUNK_SIZE_TOKENS = 600
CHUNK_OVERLAP_TOKENS = 60


def cargar_fragmentos(data_dir: Path) -> list[Document]:
    """Fragmenta cada documento Markdown y le agrega metadatos de fuente, sección y categoría."""
    catalogo = json.loads((data_dir / "catalogo.json").read_text(encoding="utf-8"))
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=CODIFICACION,
        chunk_size=CHUNK_SIZE_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        separators=["\n## ", "\n\n", "\n", ". ", " ", ""],
    )
    codificador = tiktoken.get_encoding(CODIFICACION)

    fragmentos: list[Document] = []
    for archivo in sorted(data_dir.glob("*.md")):
        if archivo.name not in catalogo:
            raise ValueError(f"{archivo.name} no tiene categoría en catalogo.json")
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
