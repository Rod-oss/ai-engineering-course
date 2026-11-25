"""API REST asíncrona del orquestador multi-agente."""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.config import REDIS_URL, WORKER_CONCURRENCY
from app.graph import construir_grafo
from app.jobs import EstadoJob, RepositorioJobs
from app.observability import iniciar_observabilidad
from app.worker import Worker

from app.state import leer_campo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")


class SolicitudTarea(BaseModel):
    tarea: str = Field(min_length=10, max_length=2000)
    simular_error: bool = Field(default=False, description="Solo para pruebas: fuerza el estado FAILED.")


class Aprobacion(BaseModel):
    aprobado: bool
    comentario: str | None = Field(default=None, max_length=500)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    await redis.ping()
    tracer = iniciar_observabilidad()
    async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
        await checkpointer.asetup()
        grafo = construir_grafo(checkpointer, redis)
        worker = Worker(grafo, RepositorioJobs(redis), tracer, WORKER_CONCURRENCY)
        worker.iniciar()
        app.state.redis, app.state.jobs, app.state.worker, app.state.grafo = redis, RepositorioJobs(redis), worker, grafo
        yield
        await worker.detener()
    await redis.aclose()


app = FastAPI(title="Kestrel: orquestador multi-agente", lifespan=lifespan)


@app.get("/health")
async def health(request: Request) -> dict:
    return {"api": "ok", "redis": await request.app.state.redis.ping()}


@app.post("/tasks", status_code=202)
async def crear_tarea(solicitud: SolicitudTarea, request: Request) -> dict:
    """Registra el job en Redis, lo encola y responde de inmediato con su job_id."""
    job_id = uuid.uuid4().hex
    await request.app.state.jobs.crear(job_id, solicitud.tarea)   # se registra ANTES de encolar
    await request.app.state.worker.encolar_inicio(job_id, solicitud.tarea, solicitud.simular_error)
    return {"job_id": job_id, "estado": EstadoJob.PENDING, "consultar": f"/tasks/{job_id}"}


@app.get("/tasks/{job_id}")
async def consultar_tarea(job_id: str, request: Request) -> dict:
    job = await request.app.state.jobs.obtener(job_id)
    if job is None:
        raise HTTPException(404, "Job no encontrado")
    return job


@app.post("/tasks/{job_id}/approve", status_code=202)
async def aprobar_tarea(job_id: str, aprobacion: Aprobacion, request: Request) -> dict:
    """Entrega la decisión humana y reanuda el grafo desde su checkpoint en Redis."""
    jobs: RepositorioJobs = request.app.state.jobs
    job = await jobs.obtener(job_id)
    if job is None:
        raise HTTPException(404, "Job no encontrado")
    if job["estado"] != EstadoJob.AWAITING_APPROVAL:
        raise HTTPException(409, f"El job no espera aprobación (estado actual: {job['estado']})")
    await jobs.actualizar(job_id, EstadoJob.PENDING, aprobacion=aprobacion.model_dump())
    await jobs.borrar_campos(job_id, "aprobacion_pendiente")
    await request.app.state.worker.encolar_reanudacion(job_id, aprobacion.model_dump())
    return {"job_id": job_id, "estado": EstadoJob.PENDING, "mensaje": "Decisión recibida; el grafo se reanudará"}


@app.get("/tasks/{job_id}/checkpoint")
async def consultar_checkpoint(job_id: str, request: Request) -> dict:
    """Muestra el último checkpoint de LangGraph guardado en Redis para este job."""
    estado = await request.app.state.grafo.aget_state({"configurable": {"thread_id": job_id}})
    if not estado.values:
        raise HTTPException(404, "No hay checkpoints para este job")
    valores = estado.values
    return {
        "checkpoint_id": estado.config["configurable"].get("checkpoint_id"),
        "siguiente_nodo": list(estado.next),
        "pasos_supervisor": valores.get("pasos_supervisor"),
        "decisiones": [leer_campo(d, "siguiente") for d in valores.get("decisiones", [])],
        "contribuciones": [leer_campo(c, "agente") for c in valores.get("contribuciones", [])],
        "accion_critica": valores.get("accion_critica"),
    }