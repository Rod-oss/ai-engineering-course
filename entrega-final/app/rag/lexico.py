"""Búsqueda léxica BM25 en memoria.

Encuentra coincidencias exactas de términos (por ejemplo kestrel-cli o pedidos.muertos) que la
búsqueda semántica puede pasar por alto. Es cálculo en memoria (sin red ni disco) y tarda
milisegundos, por eso no necesita ser asíncrona.
"""

import re

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.rag.modelos import Fragmento


def tokenizar(texto: str) -> list[str]:
    """Minúsculas y palabras completas, conservando términos como kestrel-cli o pedidos.muertos."""
    return re.findall(r"[a-záéíóúüñ0-9]+(?:[._-][a-záéíóúüñ0-9]+)*", texto.lower())


class BuscadorLexico:
    def __init__(self, documentos: list[Document]) -> None:
        if not documentos:
            raise ValueError("BM25 necesita al menos un documento")
        self.documentos = documentos
        self.bm25 = BM25Okapi([tokenizar(d.page_content) for d in documentos])

    def buscar(self, consulta: str, k: int, categoria: str | None = None) -> list[Fragmento]:
        puntajes = self.bm25.get_scores(tokenizar(consulta))
        candidatos = [
            (float(p), d)
            for p, d in zip(puntajes, self.documentos, strict=True)
            if p > 0 and (categoria is None or d.metadata["categoria"] == categoria)
        ]
        candidatos.sort(key=lambda par: par[0], reverse=True)
        return [
            Fragmento(
                chunk_id=d.metadata["chunk_id"],
                fuente=d.metadata["source"],
                categoria=d.metadata["categoria"],
                texto=d.page_content,
                metodos=["lexico"],
                puntaje=p,
            )
            for p, d in candidatos[:k]
        ]
