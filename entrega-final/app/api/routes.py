"""Rutas de la API. Todas son async y delegan el trabajo pesado al worker."""

import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.api.schemas import (
    AprobacionRecibida,
    ErrorApi,
    EstadoTarea,
    InfoCheckpoint,
    JobId,
    Salud,
    SolicitudTarea,
    TareaCreada,
)
from app.graph.state import DecisionHumana, contribuciones, decisiones
from app.services.jobs import EstadoJob, RepositorioJobs

router = APIRouter()
NO_ENCONTRADO = {404: {"model": ErrorApi, "description": "El job no existe."}}


def _jobs(request: Request) -> RepositorioJobs:
    return request.app.state.jobs


@router.get("/health", response_model=Salud, tags=["sistema"], summary="Estado de la API y de Redis")
async def health(request: Request) -> Salud:
    return Salud(redis=await request.app.state.redis.ping(), jobs_en_cola=request.app.state.worker.en_cola)


@router.post(
    "/tasks",
    response_model=TareaCreada,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["tareas"],
    summary="Crear una tarea",
    description="Registra el job en Redis, lo encola y responde de inmediato.",
)
async def crear_tarea(solicitud: SolicitudTarea, request: Request) -> TareaCreada:
    job_id = uuid.uuid4().hex
    await _jobs(request).crear(job_id, solicitud.tarea)  # se registra ANTES de encolar
    await request.app.state.worker.encolar_inicio(job_id, solicitud.tarea, solicitud.simular_error)
    return TareaCreada(job_id=job_id, estado=EstadoJob.PENDING, consultar=f"/tasks/{job_id}")


@router.get(
    "/tasks/{job_id}",
    response_model=EstadoTarea,
    responses=NO_ENCONTRADO,
    tags=["tareas"],
    summary="Consultar el estado y el resultado de un job",
)
async def consultar_tarea(job_id: JobId, request: Request) -> EstadoTarea:
    job = await _jobs(request).obtener(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job no encontrado")
    return EstadoTarea.model_validate(job)


@router.post(
    "/tasks/{job_id}/approve",
    response_model=AprobacionRecibida,
    status_code=status.HTTP_202_ACCEPTED,
    responses={**NO_ENCONTRADO, 409: {"model": ErrorApi, "description": "El job no espera aprobación."}},
    tags=["aprobación humana"],
    summary="Aprobar o rechazar una acción crítica",
)
async def aprobar_tarea(job_id: JobId, decision: DecisionHumana, request: Request) -> AprobacionRecibida:
    """Entrega la decisión humana y reanuda el grafo desde su checkpoint en Redis."""
    jobs = _jobs(request)
    job = await jobs.obtener(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job no encontrado")
    if job["estado"] != EstadoJob.AWAITING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, f"El job no espera aprobación (estado actual: {job['estado']})")
    await jobs.actualizar(job_id, EstadoJob.PENDING, aprobacion=decision.model_dump())
    await jobs.borrar_campos(job_id, "aprobacion_pendiente")
    await request.app.state.worker.encolar_reanudacion(job_id, decision.model_dump())
    return AprobacionRecibida(
        job_id=job_id, estado=EstadoJob.PENDING, mensaje="Decisión recibida; el grafo se reanudará"
    )


@router.get(
    "/tasks/{job_id}/checkpoint",
    response_model=InfoCheckpoint,
    responses=NO_ENCONTRADO,
    tags=["tareas"],
    summary="Último checkpoint de LangGraph guardado en Redis",
)
async def consultar_checkpoint(job_id: JobId, request: Request) -> InfoCheckpoint:
    estado = await request.app.state.grafo.aget_state({"configurable": {"thread_id": job_id}})
    if not estado.values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay checkpoints para este job")
    valores = estado.values
    return InfoCheckpoint(
        checkpoint_id=estado.config["configurable"].get("checkpoint_id"),
        siguiente_nodo=list(estado.next),
        pasos_supervisor=valores.get("pasos_supervisor", 0),
        decisiones=[d.siguiente for d in decisiones(valores)],
        contribuciones=[c.agente for c in contribuciones(valores)],
        accion_critica=valores.get("accion_critica", "ninguna"),
    )
