"""Grafo del orquestador con checkpointer de Redis y aprobación humana para acciones críticas."""
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.agents.analyst_agent import crear_analista
from app.agents.research_agent import crear_investigador
from app.agents.supervisor import crear_supervisor
from app.config import Settings, crear_llm, crear_vectorstore
from app.hitl import crear_nodo_aprobacion, requiere_aprobacion
from app.state import AccionCritica, Destino, EstadoOrquestador

logger = logging.getLogger("orquestador")

PROMPT_SINTESIS = """Redacta la respuesta final para el usuario, en español, a partir de las contribuciones del equipo.
- Responde directamente cada parte de la tarea.
- Usa solo cifras y reglas presentes en las contribuciones; no agregues datos nuevos.
- Indica qué dato aportó cada agente y cita las fuentes de la documentación entre corchetes.
- No supongas hechos que la tarea no menciona. Si una acción depende de una condición desconocida, preséntala como condicional.
- No menciones herramientas, canales ni plataformas que no aparezcan en las contribuciones.
- Termina con una sección breve de acciones requeridas.

Además, indica en accion_critica si la documentación exige AHORA una acción operativa con efectos secundarios:
- "revertir_despliegue" si se cumple un criterio documentado de reversión.
- "congelar_despliegues" si se cumple un criterio documentado de congelamiento.
- "ninguna" si no se exige ninguna, o si depende de datos que no se conocen."""


class SintesisFinal(BaseModel):
    respuesta: str = Field(description="Respuesta final en Markdown para el usuario.")
    accion_critica: AccionCritica = Field(description="Acción operativa con efectos secundarios que se exige ahora.")
    justificacion_accion: str = Field(description="Datos que justifican la acción; vacío si es 'ninguna'.")


def enrutar(estado: EstadoOrquestador) -> Destino:
    return estado["siguiente"]


def crear_sintesis(llm):
    sintetizador = llm.with_structured_output(SintesisFinal)

    async def sintesis(estado: EstadoOrquestador) -> dict:
        aportes = "\n\n".join(f"[{c.agente}, paso {c.paso}]\n{c.resultado}" for c in estado["contribuciones"])
        final: SintesisFinal = await sintetizador.ainvoke([
            SystemMessage(PROMPT_SINTESIS),
            HumanMessage(f"TAREA:\n{estado['tarea']}\n\nINDICACIÓN DEL SUPERVISOR:\n{estado['instruccion']}"
                         f"\n\nCONTRIBUCIONES:\n{aportes}"),
        ])
        logger.info("[sintesis] Acción crítica propuesta: %s", final.accion_critica)
        return {"respuesta_final": final.respuesta, "accion_critica": final.accion_critica,
                "justificacion_accion": final.justificacion_accion,
                "messages": [AIMessage(final.respuesta, name="sintesis")]}

    return sintesis


def construir_grafo(checkpointer: BaseCheckpointSaver, redis: Redis) -> CompiledStateGraph:
    settings = Settings.desde_entorno()
    llm = crear_llm(settings)

    grafo = StateGraph(EstadoOrquestador)
    grafo.add_node("supervisor", crear_supervisor(llm))
    grafo.add_node("investigador", crear_investigador(llm, crear_vectorstore(settings)))
    grafo.add_node("analista", crear_analista(llm))
    grafo.add_node("sintesis", crear_sintesis(llm))
    grafo.add_node("aprobacion", crear_nodo_aprobacion(redis))

    grafo.add_edge(START, "supervisor")
    grafo.add_conditional_edges("supervisor", enrutar, ["investigador", "analista", "sintesis"])
    grafo.add_edge("investigador", "supervisor")
    grafo.add_edge("analista", "supervisor")
    grafo.add_conditional_edges("sintesis", requiere_aprobacion, ["aprobacion", END])
    grafo.add_edge("aprobacion", END)
    return grafo.compile(checkpointer=checkpointer)


def estado_inicial(tarea: str) -> dict:
    return {"messages": [HumanMessage(tarea)], "tarea": tarea, "siguiente": "investigador",
            "instruccion": "", "pasos_supervisor": 0, "contribuciones": [], "decisiones": [],
            "respuesta_final": "", "accion_critica": "ninguna", "justificacion_accion": "",
            "resultado_accion": ""}