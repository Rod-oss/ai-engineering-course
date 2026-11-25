"""Esquemas Pydantic de la API. Toda entrada se valida (422 si es inválida) y toda salida se
serializa a través de un response_model, así la documentación en /docs refleja el contrato real."""

from typing import Annotated, Literal

from fastapi import Path
from pydantic import BaseModel, ConfigDict, Field

from app.graph.state import AccionCritica, DecisionHumana, Destino, SolicitudAprobacion
from app.services.jobs import EstadoJob

JobId = Annotated[
    str, Path(pattern=r"^[0-9a-f]{32}$", description="Identificador del job (32 caracteres hexadecimales).")
]

EJEMPLO_TAREA = (
    "Durante un despliegue canario la tasa de errores llegó al 2,4 % durante 6 minutos "
    "consecutivos. ¿Qué exige la documentación?"
)


class SolicitudTarea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tarea: str = Field(
        min_length=10,
        max_length=2000,
        examples=[EJEMPLO_TAREA],
        description="Pregunta o tarea en lenguaje natural sobre la plataforma Kestrel.",
    )
    simular_error: bool = Field(default=False, description="Solo para pruebas: fuerza el estado FAILED.")


class TareaCreada(BaseModel):
    job_id: str
    estado: EstadoJob
    consultar: str = Field(description="Ruta para consultar el estado del job.")


class ResultadoTarea(BaseModel):
    respuesta_final: str
    accion_critica: AccionCritica
    resultado_accion: str = ""
    flujo: list[Destino] = Field(description="Secuencia de nodos que eligió el supervisor.")


class EstadoTarea(BaseModel):
    job_id: str
    tarea: str
    estado: EstadoJob
    creado: float
    actualizado: float
    inicio: float | None = None
    fin: float | None = None
    duracion_total_s: float | None = None
    resultado: ResultadoTarea | None = None
    aprobacion_pendiente: SolicitudAprobacion | None = None
    aprobacion: DecisionHumana | None = None
    error: str | None = None
    reintentos: int = Field(default=0, description="Reintentos automáticos por errores transitorios del proveedor.")
    ultimo_error: str | None = Field(default=None, description="Último error transitorio, si hubo reintentos.")


class AprobacionRecibida(BaseModel):
    job_id: str
    estado: EstadoJob
    mensaje: str


class InfoCheckpoint(BaseModel):
    checkpoint_id: str | None
    siguiente_nodo: list[str] = Field(description="Nodos pendientes; vacío si el grafo terminó.")
    pasos_supervisor: int
    decisiones: list[Destino]
    contribuciones: list[str]
    accion_critica: AccionCritica


class Salud(BaseModel):
    api: Literal["ok"] = "ok"
    redis: bool
    jobs_en_cola: int


class ErrorApi(BaseModel):
    detail: str
