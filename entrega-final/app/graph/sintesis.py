"""Nodo de síntesis: respuesta final estructurada y propuesta de acción crítica."""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.graph.state import AccionCritica, EstadoOrquestador, contribuciones

logger = logging.getLogger("agentes")

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
    respuesta: str = Field(min_length=1, description="Respuesta final en Markdown para el usuario.")
    accion_critica: AccionCritica = Field(description="Acción operativa con efectos secundarios que se exige ahora.")
    justificacion_accion: str = Field(description="Datos que justifican la acción; vacío si es 'ninguna'.")


def crear_sintesis(llm: BaseChatModel):
    sintetizador = llm.with_structured_output(SintesisFinal)

    async def sintesis(estado: EstadoOrquestador) -> dict:
        aportes = "\n\n".join(f"[{c.agente}, paso {c.paso}]\n{c.resultado}" for c in contribuciones(estado))
        final: SintesisFinal = await sintetizador.ainvoke(
            [
                SystemMessage(PROMPT_SINTESIS),
                HumanMessage(
                    f"TAREA:\n{estado['tarea']}\n\nINDICACIÓN DEL SUPERVISOR:\n{estado['instruccion']}"
                    f"\n\nCONTRIBUCIONES:\n{aportes}"
                ),
            ]
        )
        logger.info("[sintesis] Acción crítica propuesta: %s", final.accion_critica)
        return {
            "respuesta_final": final.respuesta,
            "accion_critica": final.accion_critica,
            "justificacion_accion": final.justificacion_accion,
            "messages": [AIMessage(final.respuesta, name="sintesis")],
        }

    return sintesis
