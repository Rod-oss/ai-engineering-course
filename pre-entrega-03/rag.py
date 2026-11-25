"""Cadena RAG con LCEL y función asíncrona get_rag_response()."""
import logging

from langchain_core.documents import Document
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableParallel, RunnablePassthrough
from langchain_chroma import Chroma

from config import TOP_K, Settings, crear_llm, crear_vectorstore
from schemas import RESPUESTA_DESCONOCIDA, RespuestaRAG, ResultadoRAG

logger = logging.getLogger("rag")

parser = PydanticOutputParser(pydantic_object=RespuestaRAG)

PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Eres un asistente técnico de la plataforma Kestrel. Responde ÚNICAMENTE con la "
            "información del CONTEXTO.\n\n"
            "Reglas:\n"
            "1. Si el CONTEXTO no contiene la respuesta, responde exactamente \"No lo sé.\", con "
            "encontrada=false y sin fuentes. No uses conocimiento propio ni supongas datos.\n"
            "2. Si la respuesta está en el CONTEXTO, responde en español de forma breve y cita en "
            "fuentes las referencias de los fragmentos que usaste, por ejemplo incidentes.md#0.\n\n"
            "{format_instructions}",
        ),
        ("human", "CONTEXTO:\n{contexto}\n\nPREGUNTA: {pregunta}"),
    ]
).partial(format_instructions=parser.get_format_instructions())


def formatear_contexto(documentos: list[Document]) -> str:
    """Convierte los fragmentos recuperados en texto, cada uno con su referencia."""
    return "\n\n---\n\n".join(
        f"[{doc.metadata['ref']}]\n{doc.page_content}" for doc in documentos
    )


def verificar_vectorstore(vectorstore: Chroma, settings: Settings) -> None:
    if vectorstore._collection.count() == 0:
        raise RuntimeError("La base vectorial está vacía. Ejecuta primero: python ingest.py")
    modelo_indexado = (vectorstore._collection.metadata or {}).get("embedding_model")
    if modelo_indexado and modelo_indexado != settings.embedding_model:
        raise RuntimeError(
            f"La colección se indexó con '{modelo_indexado}' y ahora se consulta con "
            f"'{settings.embedding_model}'. Ejecuta: python ingest.py --rebuild"
        )


def construir_cadena() -> Runnable:
    settings = Settings.desde_entorno()
    vectorstore = crear_vectorstore(settings)
    verificar_vectorstore(vectorstore, settings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})

    generacion = (PROMPT | crear_llm(settings) | parser).with_retry(stop_after_attempt=3)

    return (
        RunnableParallel(docs=retriever, pregunta=RunnablePassthrough())
        | RunnablePassthrough.assign(contexto=lambda x: formatear_contexto(x["docs"]))
        | RunnablePassthrough.assign(respuesta=generacion)
    )


_cadena: Runnable | None = None


async def get_rag_response(query: str) -> ResultadoRAG:
    """Recupera fragmentos, genera una respuesta fundamentada y verifica sus fuentes."""
    global _cadena
    if _cadena is None:
        _cadena = construir_cadena()

    logger.info("Pregunta: %s", query)
    salida = await _cadena.ainvoke(query)

    recuperadas = [doc.metadata["ref"] for doc in salida["docs"]]
    logger.info("Fragmentos recuperados (top_k=%d): %s", TOP_K, ", ".join(recuperadas))

    respuesta: RespuestaRAG = salida["respuesta"]
    citadas = [fuente.strip("[] ") for fuente in respuesta.fuentes]
    fuentes = [fuente for fuente in citadas if fuente in recuperadas]
    if descartadas := set(citadas) - set(fuentes):
        logger.warning("Fuentes descartadas por no haber sido recuperadas: %s", descartadas)

    encontrada = respuesta.encontrada and bool(fuentes)
    if respuesta.encontrada and not fuentes:
        logger.warning("El modelo afirmó tener la respuesta, pero sin fuentes válidas")
    logger.info("Resultado: %s", "respuesta fundamentada" if encontrada else "fuera de contexto")

    return ResultadoRAG(
        pregunta=query,
        respuesta=respuesta.respuesta if encontrada else RESPUESTA_DESCONOCIDA,
        encontrada=encontrada,
        fuentes=fuentes if encontrada else [],
        fragmentos_recuperados=recuperadas,
    )