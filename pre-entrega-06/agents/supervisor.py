"""Supervisor: decide quién interviene, valida los resultados con una rúbrica y controla la parada."""
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from config import MAX_PASOS_SUPERVISOR
from state import Contribucion, Decision, Destino, EstadoOrquestador

logger = logging.getLogger("orquestador")

PROMPT_SUPERVISOR = """Eres el supervisor de un equipo de análisis de la plataforma ficticia Kestrel.
Dada la tarea y las contribuciones hasta ahora, decides quién debe intervenir o si es momento de finalizar.

Especialistas:
- investigador: busca datos en la documentación interna (umbrales, políticas, plazos). No calcula.
- analista: hace cálculos exactos y compara valores con umbrales. No accede a la documentación.
- sintesis: redacta la respuesta final. Elígela solo cuando la rúbrica se cumpla por completo.

Rúbrica de validación, que debes aplicar antes de elegir sintesis:
1. Datos documentados: cada umbral o política necesaria fue obtenida por el investigador, con su fuente.
2. Cálculos verificados: cada cifra fue producida por el analista con sus herramientas.
3. Coherencia: los cálculos usan exactamente los umbrales que encontró el investigador.
4. Cobertura: todas las partes de la tarea tienen respuesta.

Elige sintesis SOLO si los 4 criterios se cumplen por completo. Si alguno se cumple solo parcialmente, NO finalices: devuelve el trabajo al especialista adecuado con una instrucción de corrección concreta.
Toda comparación entre un valor medido y un umbral, por ejemplo una tasa de errores contra el límite de reversión, debe hacerla el analista con sus herramientas.
Al delegar al analista, incluye TODAS las cifras medidas de la tarea, no solo las del primer cálculo.
Escribe instrucciones autocontenidas: el especialista no ve la tarea original ni las contribuciones de otros.
Cuando delegues al analista, incluye en la instrucción las cifras medidas que debe usar.
No repitas una instrucción que ya se cumplió."""


class DecisionSupervisor(BaseModel):
    """Decisión estructurada del supervisor."""

    evaluacion: str = Field(description="Revisión breve de las contribuciones según los 4 criterios de la rúbrica.")
    siguiente: Destino = Field(description="Nodo que debe intervenir: investigador, analista o sintesis.")
    instruccion: str = Field(description="Instrucción concreta y autocontenida para el nodo elegido.")


def _resumir(contribuciones: list[Contribucion]) -> str:
    if not contribuciones:
        return "Ninguna todavía."
    return "\n\n".join(
        f"Paso {c.paso}, {c.agente} (herramientas: {', '.join(c.herramientas) or 'ninguna'}):\n{c.resultado}"
        for c in contribuciones
    )


def crear_supervisor(llm: BaseChatModel):
    decisor = llm.with_structured_output(DecisionSupervisor)

    async def supervisor(estado: EstadoOrquestador) -> dict:
        paso = estado["pasos_supervisor"] + 1
        contribuciones = estado["contribuciones"]

        if paso > MAX_PASOS_SUPERVISOR:
            decision = DecisionSupervisor(
                evaluacion=f"Se alcanzó el máximo de {MAX_PASOS_SUPERVISOR} pasos.",
                siguiente="sintesis",
                instruccion="Sintetiza con la información disponible e indica qué quedó pendiente.",
            )
        else:
            decision = await decisor.ainvoke([
                SystemMessage(PROMPT_SUPERVISOR),
                HumanMessage(f"TAREA:\n{estado['tarea']}\n\nCONTRIBUCIONES:\n{_resumir(contribuciones)}\n\n"
                             f"Paso {paso} de {MAX_PASOS_SUPERVISOR}."),
            ])
            # Validación determinista: no se puede finalizar sin el aporte de ambos especialistas.
            faltantes = [a for a in ("investigador", "analista") if not any(c.agente == a for c in contribuciones)]
            if decision.siguiente == "sintesis" and faltantes:
                logger.warning("[supervisor] Intentó finalizar sin aporte de: %s. Se corrige.", ", ".join(faltantes))
                decision = DecisionSupervisor(
                    evaluacion=decision.evaluacion + f" Falta el aporte de {faltantes[0]}.",
                    siguiente=faltantes[0],
                    instruccion=f"Aporta lo que te corresponde para resolver esta tarea: {estado['tarea']}",
                )

        logger.info("[supervisor] Paso %d -> %s\n  Evaluación: %s\n  Instrucción: %s",
                    paso, decision.siguiente, decision.evaluacion, decision.instruccion)
        return {
            "siguiente": decision.siguiente,
            "instruccion": decision.instruccion,
            "pasos_supervisor": paso,
            "decisiones": [Decision(paso=paso, **decision.model_dump())],
            "messages": [AIMessage(f"-> {decision.siguiente}: {decision.instruccion}", name="supervisor")],
        }

    return supervisor