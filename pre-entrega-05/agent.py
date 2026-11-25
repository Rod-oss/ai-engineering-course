"""Agente ReAct con LangGraph: estado, nodos, grafo y ejecución de turnos con traza."""
import logging
import operator
from typing import Annotated, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import trim_messages
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from config import MAX_TOKENS_HISTORIAL, RECURSION_LIMIT, Settings, crear_llm
from tools import HERRAMIENTAS

logger = logging.getLogger("agente")

PROMPT_SISTEMA = """Eres el asistente de atención de la tienda en línea de Nubaria, una empresa ficticia.
Respondes preguntas sobre clientes y pedidos usando EXCLUSIVAMENTE las herramientas disponibles.

Reglas:
- Decide tú qué herramientas usar y en qué orden. Si necesitas un dato que no tienes, obtenlo con una herramienta antes de responder.
- Si una herramienta devuelve un error o un resultado incompleto, analiza el mensaje y vuelve a intentarlo con datos corregidos.
- Si la información es ambigua, por ejemplo varios clientes con el mismo nombre, o falta un dato que no puedes obtener, pide una aclaración al usuario en lugar de suponer.
- Usa el contexto de la conversación para entender referencias como "el último" o "esa clienta".
- Si el usuario se refiere a algo que no aparece en la conversación, por ejemplo "el último" sin haber mencionado a ningún cliente, NO llames a ninguna herramienta: pregúntale a qué cliente o pedido se refiere.
- Nunca inventes datos. Responde en español, de forma breve, con montos en pesos mexicanos."""


class EstadoAgente(MessagesState):
    """Estado del grafo. Hereda `messages` de MessagesState, cuyo reducer agrega mensajes
    en lugar de reemplazarlos, y suma un contador acumulado con operator.add."""

    llamadas_herramientas: Annotated[int, operator.add]


def texto(mensaje: BaseMessage) -> str:
    """Extrae el texto de un mensaje, aunque el contenido venga dividido en partes."""
    if isinstance(mensaje.content, str):
        return mensaje.content
    return "".join(
        parte.get("text", "") if isinstance(parte, dict) else str(parte)
        for parte in mensaje.content
    )


def construir_grafo(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    """Arma el ciclo ReAct: modelo -> (herramientas -> modelo)* -> fin."""
    llm_con_herramientas = crear_llm(Settings.desde_entorno()).bind_tools(HERRAMIENTAS)

    async def nodo_modelo(estado: EstadoAgente) -> dict[str, Any]:
        # Recorta el historial para no enviar un contexto ilimitado (evita el "estado sucio").
        historial = trim_messages(
            estado["messages"],
            max_tokens=MAX_TOKENS_HISTORIAL,
            token_counter=count_tokens_approximately,
            strategy="last",
            start_on="human",
        )
        respuesta = await llm_con_herramientas.ainvoke([SystemMessage(PROMPT_SISTEMA), *historial])
        return {"messages": [respuesta], "llamadas_herramientas": len(respuesta.tool_calls)}

    grafo = StateGraph(EstadoAgente)
    grafo.add_node("modelo", nodo_modelo)
    grafo.add_node("herramientas", ToolNode(HERRAMIENTAS, handle_tool_errors=True))
    grafo.add_edge(START, "modelo")
    # tools_condition: si el modelo pidió herramientas va a "tools"; si no, termina.
    grafo.add_conditional_edges("modelo", tools_condition, {"tools": "herramientas", END: END})
    grafo.add_edge("herramientas", "modelo")  # el ciclo: tras observar, vuelve a razonar
    return grafo.compile(checkpointer=checkpointer)


def _describir(nodo: str, mensaje: BaseMessage) -> dict[str, Any]:
    if isinstance(mensaje, AIMessage) and mensaje.tool_calls:
        return {"nodo": nodo, "tipo": "accion",
                "herramientas": [{"nombre": c["name"], "argumentos": c["args"]} for c in mensaje.tool_calls]}
    if isinstance(mensaje, ToolMessage):
        return {"nodo": nodo, "tipo": "observacion", "herramienta": mensaje.name,
                "error": mensaje.status == "error", "resultado": texto(mensaje)}
    return {"nodo": nodo, "tipo": "respuesta", "texto": texto(mensaje)}


def _registrar(paso: dict[str, Any]) -> None:
    if paso["tipo"] == "accion":
        for llamada in paso["herramientas"]:
            logger.info("  → El agente decide usar la herramienta: %s(%s)",
                        llamada["nombre"], llamada["argumentos"])
    elif paso["tipo"] == "observacion":
        marca = "ERROR" if paso["error"] else "devuelve"
        logger.info("  → La herramienta %s %s: %s", paso["herramienta"], marca, paso["resultado"])
    else:
        logger.info("  → Respuesta: %s", paso["texto"])


async def ejecutar_turno(grafo: CompiledStateGraph, thread_id: str,
                         mensaje: str) -> tuple[str, list[dict[str, Any]]]:
    """Ejecuta un turno de conversación y devuelve la respuesta final y los pasos ReAct."""
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    pasos: list[dict[str, Any]] = []
    logger.info("[%s] Usuario: %s", thread_id, mensaje)
    try:
        async for actualizacion in grafo.astream(
            {"messages": [HumanMessage(mensaje)]}, config, stream_mode="updates"
        ):
            for nodo, datos in actualizacion.items():
                for msg in (datos or {}).get("messages", []):
                    paso = _describir(nodo, msg)
                    pasos.append(paso)
                    _registrar(paso)
    except GraphRecursionError:
        logger.warning("  → Se alcanzó el límite de %d pasos: turno detenido", RECURSION_LIMIT)
        return f"No pude completar la consulta en {RECURSION_LIMIT} pasos.", pasos

    estado = await grafo.aget_state(config)
    return texto(estado.values["messages"][-1]), pasos