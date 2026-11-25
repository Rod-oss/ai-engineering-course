"""Lógica común de los especialistas: aislamiento de contexto y registro de contribuciones."""
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.errors import GraphRecursionError

from config import RECURSION_LIMIT_ESPECIALISTA
from state import Contribucion, EstadoOrquestador

logger = logging.getLogger("orquestador")


def texto(mensaje: BaseMessage) -> str:
    if isinstance(mensaje.content, str):
        return mensaje.content
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in mensaje.content)


def crear_nodo_especialista(
    nombre: str,
    agente: Any,
    construir_entrada: Callable[[EstadoOrquestador], str],
) -> Callable[[EstadoOrquestador], Awaitable[dict]]:
    """Envuelve un agente ReAct como nodo del grafo. El agente solo recibe la entrada que
    arma `construir_entrada`, nunca el historial completo del sistema."""

    async def nodo(estado: EstadoOrquestador) -> dict:
        entrada = construir_entrada(estado)
        try:
            resultado = await agente.ainvoke(
                {"messages": [HumanMessage(entrada)]},
                {"recursion_limit": RECURSION_LIMIT_ESPECIALISTA},
            )
            mensajes = resultado["messages"]
            respuesta = texto(mensajes[-1])
            herramientas = [c["name"] for m in mensajes if isinstance(m, AIMessage) for c in m.tool_calls]
        except GraphRecursionError:
            respuesta = f"No terminé la tarea en {RECURSION_LIMIT_ESPECIALISTA} pasos."
            herramientas = []

        logger.info("[%s] Herramientas usadas: %s", nombre, ", ".join(herramientas) or "ninguna")
        logger.info("[%s] Resultado:\n%s", nombre, respuesta)
        contribucion = Contribucion(paso=estado["pasos_supervisor"], agente=nombre,
                                    instruccion=estado["instruccion"], resultado=respuesta,
                                    herramientas=herramientas)
        return {"contribuciones": [contribucion], "messages": [AIMessage(respuesta, name=nombre)]}

    return nodo