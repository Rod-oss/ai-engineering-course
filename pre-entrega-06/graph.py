"""Grafo del orquestador: supervisor jerárquico con dos especialistas y fase de síntesis."""
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.analyst_agent import crear_analista
from agents.common import texto
from agents.research_agent import crear_investigador
from agents.supervisor import crear_supervisor
from config import Settings, crear_llm, crear_vectorstore
from state import Destino, EstadoOrquestador

logger = logging.getLogger("orquestador")

PROMPT_SINTESIS = """Redacta la respuesta final para el usuario, en español, a partir de las contribuciones del equipo.
- Responde directamente cada parte de la tarea.
- Usa solo cifras y reglas presentes en las contribuciones; no agregues datos nuevos.
- Indica qué dato aportó cada agente y cita las fuentes de la documentación entre corchetes.
- No supongas hechos que la tarea no menciona. Si una acción depende de una condición desconocida, por ejemplo si hubo clientes afectados, preséntala como condicional.
- No menciones herramientas, canales ni plataformas que no aparezcan en las contribuciones.
- Termina con una sección breve de acciones requeridas."""


def enrutar(estado: EstadoOrquestador) -> Destino:
    """Arista condicional: el Literal del tipo de retorno define los destinos posibles."""
    return estado["siguiente"]


def crear_sintesis(llm):
    async def sintesis(estado: EstadoOrquestador) -> dict:
        aportes = "\n\n".join(f"[{c.agente}, paso {c.paso}]\n{c.resultado}" for c in estado["contribuciones"])
        respuesta = await llm.ainvoke([
            SystemMessage(PROMPT_SINTESIS),
            HumanMessage(f"TAREA:\n{estado['tarea']}\n\nINDICACIÓN DEL SUPERVISOR:\n{estado['instruccion']}"
                         f"\n\nCONTRIBUCIONES:\n{aportes}"),
        ])
        final = texto(respuesta)
        logger.info("[sintesis] Respuesta final:\n%s", final)
        return {"respuesta_final": final, "messages": [AIMessage(final, name="sintesis")]}

    return sintesis


def construir_grafo() -> CompiledStateGraph:
    settings = Settings.desde_entorno()
    llm = crear_llm(settings)

    grafo = StateGraph(EstadoOrquestador)
    grafo.add_node("supervisor", crear_supervisor(llm))
    grafo.add_node("investigador", crear_investigador(llm, crear_vectorstore(settings)))
    grafo.add_node("analista", crear_analista(llm))
    grafo.add_node("sintesis", crear_sintesis(llm))

    grafo.add_edge(START, "supervisor")
    grafo.add_conditional_edges("supervisor", enrutar, ["investigador", "analista", "sintesis"])
    grafo.add_edge("investigador", "supervisor")   # cada especialista reporta al supervisor
    grafo.add_edge("analista", "supervisor")
    grafo.add_edge("sintesis", END)
    return grafo.compile()


def estado_inicial(tarea: str) -> dict:
    return {"messages": [HumanMessage(tarea)], "tarea": tarea, "siguiente": "investigador",
            "instruccion": "", "pasos_supervisor": 0, "contribuciones": [], "decisiones": [],
            "respuesta_final": ""}