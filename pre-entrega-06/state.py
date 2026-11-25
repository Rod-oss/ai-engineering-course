"""Estado compartido del orquestador: registra quién aportó qué y controla el flujo."""
import operator
from typing import Annotated, Literal

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field

Destino = Literal["investigador", "analista", "sintesis"]


class Contribucion(BaseModel):
    """Lo que aportó un especialista en un paso concreto del flujo."""

    paso: int
    agente: str
    instruccion: str
    resultado: str
    herramientas: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    """Registro de una decisión del supervisor."""

    paso: int
    siguiente: Destino
    instruccion: str
    evaluacion: str


class EstadoOrquestador(MessagesState):
    """Hereda `messages` de MessagesState y agrega el control del flujo multi-agente."""

    tarea: str                                                   # solicitud original del usuario
    siguiente: Destino                                           # nodo elegido por el supervisor
    instruccion: str                                             # instrucción para ese nodo
    pasos_supervisor: int                                        # contador contra bucles infinitos
    contribuciones: Annotated[list[Contribucion], operator.add]  # historial de aportes, se acumula
    decisiones: Annotated[list[Decision], operator.add]          # historial de decisiones, se acumula
    respuesta_final: str