"""Búsqueda semántica en Pinecone con el cliente asíncrono oficial (PineconeAsyncio).

En la Pre-entrega 4 las consultas asíncronas concurrentes fallaban con "Session is closed"
porque cada búsqueda abría y cerraba su propia sesión HTTP. Aquí la sesión se abre UNA vez
al arrancar la API (abrir_indice) y se cierra al apagarla, y todas las búsquedas la comparten.
"""

from langchain_core.embeddings import Embeddings
from pinecone import PineconeAsyncio

from app.rag.modelos import Fragmento
from app.settings import Settings


class ConexionPinecone:
    """Cliente e índice asíncronos de Pinecone, abiertos durante toda la vida de la API."""

    def __init__(self, cliente: PineconeAsyncio, indice) -> None:
        self.cliente = cliente
        self.indice = indice

    @classmethod
    async def abrir(cls, settings: Settings) -> "ConexionPinecone":
        cliente = PineconeAsyncio(api_key=settings.pinecone_api_key.get_secret_value())
        try:
            if not await cliente.has_index(settings.pinecone_index):
                raise RuntimeError(
                    f"No existe el índice '{settings.pinecone_index}'. Créalo con: python scripts/ingestar.py"
                )
            descripcion = await cliente.describe_index(settings.pinecone_index)
        except BaseException:
            await cliente.close()
            raise
        return cls(cliente, cliente.IndexAsyncio(host=descripcion.host))

    async def cerrar(self) -> None:
        await self.indice.close()
        await self.cliente.close()


class BuscadorVectorial:
    def __init__(self, indice, embeddings: Embeddings, namespace: str) -> None:
        self.indice = indice
        self.embeddings = embeddings
        self.namespace = namespace

    async def buscar(self, consulta: str, k: int, categoria: str | None = None) -> list[Fragmento]:
        vector = await self.embeddings.aembed_query(consulta)
        filtro = {"categoria": {"$eq": categoria}} if categoria else None
        respuesta = await self.indice.query(
            vector=vector, top_k=k, namespace=self.namespace, filter=filtro, include_metadata=True
        )
        return [
            Fragmento(
                chunk_id=str(m.metadata.get("chunk_id", m.id)),
                fuente=str(m.metadata.get("source", "")),
                categoria=str(m.metadata.get("categoria", "")),
                texto=str(m.metadata.get("text", "")),
                metodos=["vectorial"],
                puntaje=float(m.score or 0.0),
            )
            for m in respuesta.matches
        ]
