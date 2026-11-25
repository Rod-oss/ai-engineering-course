"""Agente investigador: busca información en la documentación de Kestrel (Pinecone)."""
import asyncio

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from langchain_pinecone import PineconeVectorStore
from langgraph.prebuilt import create_react_agent

from app.agents.common import crear_nodo_especialista
from app.config import TOP_K
from app.state import EstadoOrquestador

PROMPT_INVESTIGADOR = """Eres el investigador de un equipo de análisis de la plataforma ficticia Kestrel.
Tu única fuente es la documentación interna, que consultas con la herramienta buscar_documentacion.

- Haz una búsqueda por cada tema que necesites; puedes llamar a la herramienta varias veces.
- Responde con los datos EXACTOS encontrados (cifras, umbrales, plazos y reglas) y cita la fuente de cada dato entre corchetes, por ejemplo [despliegues-00].
- No hagas cálculos ni conclusiones: eso le corresponde al analista.
- Si algo no aparece en la documentación, dilo explícitamente en lugar de suponerlo."""


def crear_herramienta_busqueda(vectorstore: PineconeVectorStore):
    @tool
    async def buscar_documentacion(consulta: str, categoria: str | None = None) -> str:
        """Busca en la documentación interna de Kestrel los fragmentos más relevantes para una
        consulta en lenguaje natural.

        Devuelve hasta 4 fragmentos, cada uno con su identificador y archivo de origen.
        Usa `categoria` solo para acotar la búsqueda: "arquitectura", "api", "operaciones"
        (incidentes, monitoreo, respaldos), "procesos" (despliegues, onboarding) o "seguridad".
        Si no estás seguro de la categoría, no la indiques.
        """
        filtro = {"categoria": {"$eq": categoria}} if categoria else None
        # La búsqueda síncrona en un hilo evita el error de sesión del cliente asíncrono (Pre-entrega 4).
        documentos = await asyncio.to_thread(vectorstore.similarity_search, consulta, k=TOP_K, filter=filtro)
        if not documentos:
            return "Sin resultados para esa consulta."
        return "\n\n---\n\n".join(
            f"[{d.metadata['chunk_id']} | {d.metadata['source']}]\n{d.page_content}" for d in documentos
        )

    return buscar_documentacion


def entrada_investigador(estado: EstadoOrquestador) -> str:
    # Solo la instrucción del supervisor: el investigador no necesita el resto del contexto.
    return estado["instruccion"]


def crear_investigador(llm: BaseChatModel, vectorstore: PineconeVectorStore):
    agente = create_react_agent(llm, [crear_herramienta_busqueda(vectorstore)], prompt=PROMPT_INVESTIGADOR)
    return crear_nodo_especialista("investigador", agente, entrada_investigador)