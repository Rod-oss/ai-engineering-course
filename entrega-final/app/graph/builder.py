"""Construcción del grafo de agentes.

ensamblar_grafo() solo define la topología (nodos y aristas). Así la misma estructura se usa en
producción (con LLM, Pinecone y Redis), en las pruebas automáticas (con nodos falsos) y para
exportar el diagrama (scripts/exportar_grafo.py) sin claves ni red.
"""

from collections.abc import Callable, Mapping

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.analyst_agent import crear_analista
from app.agents.research_agent import crear_investigador
from app.agents.supervisor import crear_supervisor
from app.graph.hitl import RegistroAuditoria, crear_nodo_aprobacion, requiere_aprobacion
from app.graph.sintesis import crear_sintesis
from app.graph.state import Destino, EstadoOrquestador
from app.rag.hibrido import RecuperadorHibrido
from app.settings import Settings

NODOS = ("supervisor", "investigador", "analista", "sintesis", "aprobacion")


def enrutar(estado: EstadoOrquestador) -> Destino:
    return estado["siguiente"]


def ensamblar_grafo(
    nodos: Mapping[str, Callable], checkpointer: BaseCheckpointSaver | None = None
) -> CompiledStateGraph:
    grafo = StateGraph(EstadoOrquestador)
    for nombre in NODOS:
        grafo.add_node(nombre, nodos[nombre])

    grafo.add_edge(START, "supervisor")
    grafo.add_conditional_edges("supervisor", enrutar, ["investigador", "analista", "sintesis"])
    grafo.add_edge("investigador", "supervisor")
    grafo.add_edge("analista", "supervisor")
    grafo.add_conditional_edges("sintesis", requiere_aprobacion, ["aprobacion", END])
    grafo.add_edge("aprobacion", END)
    return grafo.compile(checkpointer=checkpointer)


def construir_grafo(
    settings: Settings,
    llm,
    recuperador: RecuperadorHibrido,
    auditoria: RegistroAuditoria,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    nodos = {
        "supervisor": crear_supervisor(llm, settings.max_pasos_supervisor),
        "investigador": crear_investigador(llm, recuperador, settings.recursion_limit_especialista),
        "analista": crear_analista(llm, settings.recursion_limit_especialista),
        "sintesis": crear_sintesis(llm),
        "aprobacion": crear_nodo_aprobacion(auditoria),
    }
    return ensamblar_grafo(nodos, checkpointer)
