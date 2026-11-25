"""Worker: ejecuta los jobs en segundo plano con concurrencia limitada y registra su estado en Redis."""
import asyncio
import logging
import time
from app.state import leer_campo
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from opentelemetry.trace import Tracer

from app.config import RECURSION_LIMIT_GRAFO
from app.graph import estado_inicial
from app.jobs import EstadoJob, RepositorioJobs

logger = logging.getLogger("worker")



class Worker:
    """Consume una cola en memoria con N tareas asíncronas, de modo que la API nunca espera al grafo."""

    def __init__(self, grafo: CompiledStateGraph, jobs: RepositorioJobs, tracer: Tracer, concurrencia: int) -> None:
        self.grafo, self.jobs, self.tracer, self.concurrencia = grafo, jobs, tracer, concurrencia
        self.cola: asyncio.Queue = asyncio.Queue()
        self._tareas: list[asyncio.Task] = []

    def iniciar(self) -> None:
        self._tareas = [asyncio.create_task(self._bucle(i)) for i in range(self.concurrencia)]
        logger.info("Worker iniciado con concurrencia %d", self.concurrencia)

    async def detener(self) -> None:
        for tarea in self._tareas:
            tarea.cancel()
        await asyncio.gather(*self._tareas, return_exceptions=True)

    async def encolar_inicio(self, job_id: str, tarea: str, simular_error: bool = False) -> None:
        await self.cola.put(("iniciar", job_id, {"tarea": tarea, "simular_error": simular_error}))

    async def encolar_reanudacion(self, job_id: str, decision: dict) -> None:
        await self.cola.put(("reanudar", job_id, decision))

    async def _bucle(self, numero: int) -> None:
        while True:
            tipo, job_id, datos = await self.cola.get()
            try:
                await self._procesar(tipo, job_id, datos)
            except Exception as exc:  # cualquier fallo deja el job en FAILED: el cliente nunca espera para siempre
                logger.exception("[worker %d] Job %s falló", numero, job_id)
                await self.jobs.actualizar(job_id, EstadoJob.FAILED, error=f"{type(exc).__name__}: {exc}", fin=time.time())
            finally:
                self.cola.task_done()

    async def _procesar(self, tipo: str, job_id: str, datos: dict) -> None:
        campos = {"inicio": time.time()} if tipo == "iniciar" else {}
        await self.jobs.actualizar(job_id, EstadoJob.RUNNING, **campos)
        config = {"configurable": {"thread_id": job_id}, "recursion_limit": RECURSION_LIMIT_GRAFO}

        with self.tracer.start_as_current_span(f"job.{tipo}", openinference_span_kind="chain") as span:
            span.set_attribute("job.id", job_id)
            if tipo == "iniciar":
                if datos["simular_error"]:
                    raise RuntimeError("Error simulado para verificar el estado FAILED")
                entrada = estado_inicial(datos["tarea"])
            else:
                entrada = Command(resume=datos)
            await self.grafo.ainvoke(entrada, config)

        estado = await self.grafo.aget_state(config)
        interrupciones = getattr(estado, "interrupts", ()) or tuple(i for t in estado.tasks for i in t.interrupts)
        if interrupciones:
            await self.jobs.actualizar(job_id, EstadoJob.AWAITING_APPROVAL, aprobacion_pendiente=interrupciones[0].value)
            logger.info("Job %s en espera de aprobación humana", job_id)
            return

        valores = estado.values
        await self.jobs.actualizar(job_id, EstadoJob.DONE, fin=time.time(), resultado={
            "respuesta_final": valores["respuesta_final"],
            "accion_critica": valores["accion_critica"],
            "resultado_accion": valores.get("resultado_accion", ""),
            "flujo": [leer_campo(d, "siguiente") for d in valores["decisiones"]],
        })
        logger.info("Job %s terminado", job_id)