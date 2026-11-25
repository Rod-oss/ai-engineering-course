"""Worker: ejecuta los jobs en segundo plano con concurrencia limitada y registra su estado en Redis.

Persistencia ante reinicios: la cola vive en memoria, pero el estado de cada job y los checkpoints
del grafo viven en Redis. Al arrancar, recuperar_pendientes() revisa los jobs que quedaron a medias
y los retoma desde su último checkpoint, sin repetir los pasos ya terminados.
"""

import asyncio
import logging
import time
from typing import Any, Literal

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from opentelemetry.trace import Status, StatusCode, Tracer

from app.graph.state import decisiones, estado_inicial
from app.services.jobs import EstadoJob, RepositorioJobs

logger = logging.getLogger("worker")

TipoTrabajo = Literal["iniciar", "reanudar", "continuar"]


def _interrupciones(estado) -> tuple:
    return getattr(estado, "interrupts", ()) or tuple(i for t in estado.tasks for i in t.interrupts)


class Worker:
    """Consume una cola en memoria con N tareas asíncronas, de modo que la API nunca espera al grafo."""

    def __init__(
        self, grafo: CompiledStateGraph, jobs: RepositorioJobs, tracer: Tracer, concurrencia: int, recursion_limit: int
    ) -> None:
        self.grafo, self.jobs, self.tracer = grafo, jobs, tracer
        self.concurrencia, self.recursion_limit = concurrencia, recursion_limit
        self.cola: asyncio.Queue[tuple[TipoTrabajo, str, dict]] = asyncio.Queue()
        self._tareas: list[asyncio.Task] = []

    def iniciar(self) -> None:
        self._tareas = [asyncio.create_task(self._bucle(i)) for i in range(self.concurrencia)]
        logger.info("Worker iniciado con concurrencia %d", self.concurrencia)

    async def detener(self) -> None:
        for tarea in self._tareas:
            tarea.cancel()
        await asyncio.gather(*self._tareas, return_exceptions=True)

    @property
    def en_cola(self) -> int:
        return self.cola.qsize()

    async def encolar_inicio(self, job_id: str, tarea: str, simular_error: bool = False) -> None:
        await self.cola.put(("iniciar", job_id, {"tarea": tarea, "simular_error": simular_error}))

    async def encolar_reanudacion(self, job_id: str, decision: dict) -> None:
        await self.cola.put(("reanudar", job_id, decision))

    async def recuperar_pendientes(self) -> int:
        """Retoma los jobs PENDING o RUNNING que quedaron a medias por un reinicio."""
        recuperados = 0
        async for job_id in self.jobs.ids():
            job = await self.jobs.obtener(job_id)
            if not job or job["estado"] not in (EstadoJob.PENDING, EstadoJob.RUNNING):
                continue
            estado = await self.grafo.aget_state(self._config(job_id))
            if not estado.values:
                await self.encolar_inicio(job_id, job["tarea"])  # nunca llegó a empezar
            elif _interrupciones(estado):
                if "aprobacion" in job:  # ya había una decisión humana
                    await self.encolar_reanudacion(job_id, job["aprobacion"])
                else:
                    await self.jobs.actualizar(
                        job_id, EstadoJob.AWAITING_APPROVAL, aprobacion_pendiente=_interrupciones(estado)[0].value
                    )
                    continue
            else:
                await self.cola.put(("continuar", job_id, {}))  # sigue desde el último checkpoint
            recuperados += 1
            logger.info("Job %s recuperado tras el reinicio", job_id)
        return recuperados

    def _config(self, job_id: str) -> dict:
        return {"configurable": {"thread_id": job_id}, "recursion_limit": self.recursion_limit}

    async def _bucle(self, numero: int) -> None:
        while True:
            tipo, job_id, datos = await self.cola.get()
            try:
                await self._procesar(tipo, job_id, datos)
            except Exception as exc:  # cualquier fallo deja el job en FAILED: el cliente nunca espera para siempre
                logger.exception("[worker %d] Job %s falló", numero, job_id)
                await self.jobs.actualizar(
                    job_id, EstadoJob.FAILED, error=f"{type(exc).__name__}: {exc}", fin=time.time()
                )
            finally:
                self.cola.task_done()

    async def _procesar(self, tipo: TipoTrabajo, job_id: str, datos: dict[str, Any]) -> None:
        job = await self.jobs.obtener(job_id) or {}
        campos = {} if "inicio" in job else {"inicio": time.time()}
        await self.jobs.actualizar(job_id, EstadoJob.RUNNING, **campos)
        config = self._config(job_id)

        with self.tracer.start_as_current_span(f"job.{tipo}", openinference_span_kind="chain") as span:
            span.set_attribute("job.id", job_id)
            span.set_attribute("session.id", job_id)  # Phoenix agrupa las trazas de un mismo job en Sessions
            span.set_attribute("input.value", job.get("tarea", ""))
            if tipo == "iniciar":
                if datos["simular_error"]:
                    error = RuntimeError("Error simulado para verificar el estado FAILED")
                    span.set_status(Status(StatusCode.ERROR, str(error)))
                    raise error
                entrada: Any = estado_inicial(datos["tarea"])
            elif tipo == "reanudar":
                entrada = Command(resume=datos)
            else:
                entrada = None  # continuar: LangGraph retoma desde el último checkpoint guardado
            await self.grafo.ainvoke(entrada, config)

            estado = await self.grafo.aget_state(config)
            interrupciones = _interrupciones(estado)
            if interrupciones:
                span.set_attribute("output.value", "AWAITING_APPROVAL")
                await self.jobs.actualizar(
                    job_id, EstadoJob.AWAITING_APPROVAL, aprobacion_pendiente=interrupciones[0].value
                )
                logger.info("Job %s en espera de aprobación humana", job_id)
                return

            valores = estado.values
            span.set_attribute("output.value", valores.get("respuesta_final", ""))
            await self.jobs.actualizar(
                job_id,
                EstadoJob.DONE,
                fin=time.time(),
                resultado={
                    "respuesta_final": valores["respuesta_final"],
                    "accion_critica": valores["accion_critica"],
                    "resultado_accion": valores.get("resultado_accion", ""),
                    "flujo": [d.siguiente for d in decisiones(valores)],
                },
            )
            logger.info("Job %s terminado", job_id)
