"""Estado compartido del grafo y modelos Pydantic del dominio.

Decisión de diseño: las contribuciones y decisiones se VALIDAN con Pydantic al crearse, pero se
GUARDAN en el estado como diccionarios (model_dump). Así el checkpoint en Redis contiene solo JSON
y, al reanudar tras un reinicio, los datos vuelven con el mismo formato. En la Pre-entrega 7 los
objetos Pydantic volvían de Redis como diccionarios y rompían la reanudación (KeyError).
Para leerlos con tipos se usan contribuciones() y decisiones(), que los validan de nuevo.
"""

import operator
from typing import Annotated, Any, Literal

from langchain_core.messages import HumanMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel, ConfigDict, Field

Destino = Literal["investigador", "analista", "sintesis"]
AccionCritica = Literal["ninguna", "revertir_despliegue", "congelar_despliegues"]


class Contribucion(BaseModel):
    paso: int = Field(ge=0)
    agente: Literal["investigador", "analista"]
    instruccion: str
    resultado: str
    herramientas: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    paso: int = Field(ge=1)
    siguiente: Destino
    instruccion: str
    evaluacion: str


class SolicitudAprobacion(BaseModel):
    """Lo que el grafo entrega al pausarse con interrupt() y la API muestra al revisor."""

    accion: AccionCritica
    descripcion: str
    justificacion: str
    como_responder: str


class DecisionHumana(BaseModel):
    """Respuesta del revisor humano. Se valida al recibirla en la API y otra vez dentro del grafo."""

    model_config = ConfigDict(extra="forbid")

    aprobado: bool
    comentario: str | None = Field(default=None, max_length=500)


class EstadoOrquestador(MessagesState):
    tarea: str
    siguiente: Destino
    instruccion: str
    pasos_supervisor: int
    contribuciones: Annotated[list[dict], operator.add]
    decisiones: Annotated[list[dict], operator.add]
    respuesta_final: str
    accion_critica: AccionCritica
    justificacion_accion: str
    resultado_accion: str


def a_modelo[M: BaseModel](modelo: type[M], registro: Any) -> M:
    """Convierte un registro del estado (objeto, dict o dict serializado por LangChain) en el modelo."""
    if isinstance(registro, modelo):
        return registro
    if isinstance(registro, dict) and isinstance(registro.get("kwargs"), dict) and "lc" in registro:
        registro = registro["kwargs"]
    return modelo.model_validate(registro)


def contribuciones(estado: dict) -> list[Contribucion]:
    return [a_modelo(Contribucion, c) for c in estado.get("contribuciones", [])]


def decisiones(estado: dict) -> list[Decision]:
    return [a_modelo(Decision, d) for d in estado.get("decisiones", [])]


def estado_inicial(tarea: str) -> dict:
    return {
        "messages": [HumanMessage(tarea)],
        "tarea": tarea,
        "siguiente": "investigador",
        "instruccion": "",
        "pasos_supervisor": 0,
        "contribuciones": [],
        "decisiones": [],
        "respuesta_final": "",
        "accion_critica": "ninguna",
        "justificacion_accion": "",
        "resultado_accion": "",
    }
