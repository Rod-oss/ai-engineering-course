"""Estado compartido del orquestador, con los campos del flujo de aprobación humana."""
import operator
from typing import Any
from typing import Annotated, Literal

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field

Destino = Literal["investigador", "analista", "sintesis"]
AccionCritica = Literal["ninguna", "revertir_despliegue", "congelar_despliegues"]


class Contribucion(BaseModel):
    paso: int
    agente: str
    instruccion: str
    resultado: str
    herramientas: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    paso: int
    siguiente: Destino
    instruccion: str
    evaluacion: str


class EstadoOrquestador(MessagesState):
    tarea: str
    siguiente: Destino
    instruccion: str
    pasos_supervisor: int
    contribuciones: Annotated[list[Contribucion], operator.add]
    decisiones: Annotated[list[Decision], operator.add]
    respuesta_final: str
    accion_critica: AccionCritica      # acción con efectos secundarios propuesta por la síntesis
    justificacion_accion: str
    resultado_accion: str              # qué pasó tras la revisión humana

def leer_campo(registro: Any, nombre: str) -> Any:
    """Lee un campo de una Contribucion o Decision, sea un objeto Pydantic o un dict leído de Redis."""
    if hasattr(registro, nombre):
        return getattr(registro, nombre)
    if isinstance(registro, dict):
        if nombre in registro:
            return registro[nombre]
        kwargs = registro.get("kwargs")
        if isinstance(kwargs, dict) and nombre in kwargs:
            return kwargs[nombre]
    raise KeyError(f"No se encontró '{nombre}' en {type(registro).__name__}: {str(registro)[:200]}")