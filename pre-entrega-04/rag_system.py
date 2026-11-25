"""RAGSystem: recuperador híbrido que combina Pinecone (semántico) y BM25 (léxico)."""
import asyncio
import re

from dotenv import load_dotenv
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_pinecone import PineconeVectorStore

try:
    from langchain_classic.retrievers import EnsembleRetriever
except ImportError:  # versiones anteriores de LangChain
    from langchain.retrievers import EnsembleRetriever

from config import NAMESPACE, TOP_K, Settings, crear_cliente_pinecone, crear_embeddings
from documents import cargar_fragmentos

MODOS = ("vectorial", "lexico", "hibrido")


def tokenizar(texto: str) -> list[str]:
    """Minúsculas y palabras completas, conservando términos como kestrel-cli o pedidos.muertos."""
    return re.findall(r"[a-záéíóúüñ0-9]+(?:[._-][a-záéíóúüñ0-9]+)*", texto.lower())


class RAGSystem:
    """Encapsula un EnsembleRetriever que fusiona búsqueda semántica y léxica."""

    def __init__(self, k: int = TOP_K, pesos: tuple[float, float] = (0.5, 0.5)) -> None:
        settings = Settings.desde_entorno()
        self.k = k
        self.pesos = pesos
        self.fragmentos = cargar_fragmentos()
        index = crear_cliente_pinecone(settings).Index(settings.index_name)
        self.vectorstore = PineconeVectorStore(
            index=index, embedding=crear_embeddings(settings), namespace=NAMESPACE, text_key="text"
        )
        self._hibridos: dict[str | None, EnsembleRetriever] = {}

    def retriever_vectorial(self, categoria: str | None = None) -> BaseRetriever:
        busqueda = {"k": self.k}
        if categoria:
            busqueda["filter"] = {"categoria": {"$eq": categoria}}
        return self.vectorstore.as_retriever(search_kwargs=busqueda)

    def retriever_lexico(self, categoria: str | None = None) -> BaseRetriever:
        documentos = [d for d in self.fragmentos
                      if categoria is None or d.metadata["categoria"] == categoria]
        return BM25Retriever.from_documents(documentos, k=self.k, preprocess_func=tokenizar)

    def retriever_hibrido(self, categoria: str | None = None) -> EnsembleRetriever:
        if categoria not in self._hibridos:
            self._hibridos[categoria] = EnsembleRetriever(
                retrievers=[self.retriever_vectorial(categoria), self.retriever_lexico(categoria)],
                weights=list(self.pesos),
                id_key="chunk_id",  # evita duplicados cuando ambos traen el mismo fragmento
            )
        return self._hibridos[categoria]

    def _retriever(self, modo: str, categoria: str | None) -> BaseRetriever:
        if modo not in MODOS:
            raise ValueError(f"Modo desconocido: {modo}. Opciones: {', '.join(MODOS)}")
        return {
            "vectorial": self.retriever_vectorial,
            "lexico": self.retriever_lexico,
            "hibrido": self.retriever_hibrido,
        }[modo](categoria)

    def buscar(self, consulta: str, modo: str = "hibrido",
               categoria: str | None = None) -> list[Document]:
        """Devuelve los top-k fragmentos (por defecto, combinando léxico y semántico)."""
        return self._retriever(modo, categoria).invoke(consulta)[: self.k]

    async def abuscar(self, consulta: str, modo: str = "hibrido",
                      categoria: str | None = None) -> list[Document]:
        """Versión asíncrona de buscar()."""
        return (await self._retriever(modo, categoria).ainvoke(consulta))[: self.k]


async def _demo() -> None:
    rag = RAGSystem()
    consulta = "¿Qué hace el comando kestrel-cli db restaurar?"
    print(f"\nConsulta: {consulta}")
    for modo in MODOS:
        documentos = await rag.abuscar(consulta, modo=modo)
        print(f"  {modo:<10} -> {[d.metadata['chunk_id'] for d in documentos]}")

    consulta = "¿Cómo se obtiene acceso temporal a producción?"
    documentos = await rag.abuscar(consulta, categoria="seguridad")
    print(f"\nConsulta filtrada por categoría 'seguridad': {consulta}")
    print(f"  hibrido    -> {[d.metadata['chunk_id'] for d in documentos]}")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(_demo())