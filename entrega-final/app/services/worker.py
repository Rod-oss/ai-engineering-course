"""Worker: ejecuta los jobs en segundo plano con concurrencia limitada y registra su estado en Redis.

Persistencia ante reinicios: la cola vive en memoria, pero el estado de cada job y los checkpoints
del grafo viven en Redis. Al arrancar, recuperar_pendientes() revisa los jobs que quedaron a medias
y los retoma desde su último checkpoint, sin repetir los pasos ya terminados.

Resiliencia ante errores transitorios: si el proveedor responde 503 (sobrecarga), 429 (límite) o hay
un timeout, el job no falla de inmediato. Vuelve a PENDING y se reintenta desde su último checkpoint,
con espera exponencial, hasta max_reintentos veces. Los errores permanentes van directo a FAILED.
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


MARCAS_TRANSITORIAS = ("503 UNAVAILABLE", "429 RESOURCE_EXHAUSTED", "500 INTERNAL", "DEADLINE_EXCEEDED")
CODIGOS_TRANSITORIOS = {429, 500, 502, 503, 504}


def es_transitorio(exc: BaseException) -> bool:
    """True si el error (o alguna de sus causas) es temporal y vale la pena reintentar."""
    actual: BaseException | None = exc
    vistos: set[int] = set()
    while actual is not None and id(actual) not in vistos:
        vistos.add(id(actual))
        if isinstance(actual, (TimeoutError, ConnectionError)):
            return True
        if (
            getattr(actual, "code", None) in CODIGOS_TRANSITORIOS
            or getattr(actual, "status_code", None) in CODIGOS_TRANSITORIOS
        ):
            return True
        if any(marca in str(actual) for marca in MARCAS_TRANSITORIAS):
            return True
        actual = actual.__cause__ or actual.__context__
    return False


def _interrupciones(estado) -> tuple:
    return getattr(estado, "interrupts", ()) or tuple(i for t in estado.tasks for i in t.interrupts)


class Worker:
    """Consume una cola en memoria con N tareas asíncronas, de modo que la API nunca espera al grafo."""

    def __init__(
        self,
        grafo: CompiledStateGraph,
        jobs: RepositorioJobs,
        tracer: Tracer,
        concurrencia: int,
        recursion_limit: int,
        max_reintentos: int = 3,
        espera_reintento_s: float = 20,
    ) -> None:
        self.grafo, self.jobs, self.tracer = grafo, jobs, tracer
        self.concurrencia, self.recursion_limit = concurrencia, recursion_limit
        self.max_reintentos, self.espera_reintento_s = max_reintentos, espera_reintento_s
        self.cola: asyncio.Queue[tuple[TipoTrabajo, str, dict]] = asyncio.Queue()
        self._tareas: list[asyncio.Task] = []
        self._reintentos_programados: set[asyncio.Task] = set()

    def iniciar(self) -> None:
        self._tareas = [asyncio.create_task(self._bucle(i)) for i in range(self.concurrencia)]
        logger.info("Worker iniciado con concurrencia %d", self.concurrencia)

    async def detener(self) -> None:
        for tarea in [*self._tareas, *self._reintentos_programados]:
            tarea.cancel()
        await asyncio.gather(*self._tareas, *self._reintentos_programados, return_exceptions=True)

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
            if await self._encolar_retoma(job_id, job):
                recuperados += 1
                logger.info("Job %s recuperado tras el reinicio", job_id)
        return recuperados

    async def _encolar_retoma(self, job_id: str, job: dict) -> bool:
        """Encola lo necesario para retomar el job desde su último checkpoint. False si queda en pausa HITL."""
        estado = await self.grafo.aget_state(self._config(job_id))
        if not estado.values:
            await self.encolar_inicio(job_id, job["tarea"])  # nunca llegó a guardar un checkpoint
        elif _interrupciones(estado):
            if "aprobacion" not in job:  # sigue esperando la decisión humana
                await self.jobs.actualizar(
                    job_id, EstadoJob.AWAITING_APPROVAL, aprobacion_pendiente=_interrupciones(estado)[0].value
                )
                return False
            await self.encolar_reanudacion(job_id, job["aprobacion"])  # ya había una decisión humana
        else:
            await self.cola.put(("continuar", job_id, {}))  # sigue desde el último checkpoint
        return True

    def _config(self, job_id: str) -> dict:
        return {"configurable": {"thread_id": job_id}, "recursion_limit": self.recursion_limit}

    async def _bucle(self, numero: int) -> None:
        while True:
            tipo, job_id, datos = await self.cola.get()
            try:
                await self._procesar(tipo, job_id, datos)
            except Exception as exc:  # ningún fallo deja al cliente esperando para siempre
                await self._manejar_error(numero, job_id, exc)
            finally:
                self.cola.task_done()

    async def _manejar_error(self, numero: int, job_id: str, exc: Exception) -> None:
        job = await self.jobs.obtener(job_id) or {}
        intentos = int(job.get("reintentos", 0))
        descripcion = f"{type(exc).__name__}: {exc}"
        if es_transitorio(exc) and intentos < self.max_reintentos:
            espera = self.espera_reintento_s * 2**intentos
            logger.warning(
                "[worker %d] Job %s: error transitorio (%s). Reintento %d de %d en %.0f s desde el último checkpoint",
                numero,
                job_id,
                type(exc).__name__,
                intentos + 1,
                self.max_reintentos,
                espera,
            )
            await self.jobs.actualizar(
                job_id, EstadoJob.PENDING, reintentos=intentos + 1, ultimo_error=descripcion[:500]
            )
            tarea = asyncio.create_task(self._reintentar_tras(espera, job_id))
            self._reintentos_programados.add(tarea)
            tarea.add_done_callback(self._reintentos_programados.discard)
            return
        logger.error("[worker %d] Job %s falló", numero, job_id, exc_info=exc)
        await self.jobs.actualizar(job_id, EstadoJob.FAILED, error=descripcion, fin=time.time())

    async def _reintentar_tras(self, espera: float, job_id: str) -> None:
        await asyncio.sleep(espera)
        job = await self.jobs.obtener(job_id)
        if job and job["estado"] == EstadoJob.PENDING:
            await self._encolar_retoma(job_id, job)

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
