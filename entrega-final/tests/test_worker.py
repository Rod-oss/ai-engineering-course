"""Worker: estados del job, FAILED y recuperación tras un reinicio."""

import asyncio

from langgraph.checkpoint.memory import InMemorySaver

from app.graph.builder import ensamblar_grafo
from app.services.jobs import EstadoJob
from app.services.worker import Worker, es_transitorio
from tests.fakes import RedisFalso, RepositorioFalso, TracerFalso, nodos_completos

JOB = "a" * 32


def crear_worker(checkpointer, jobs, **kwargs) -> Worker:
    grafo = ensamblar_grafo(nodos_completos(RedisFalso(), **kwargs), checkpointer)
    return Worker(grafo, jobs, TracerFalso(), concurrencia=1, recursion_limit=25)


def test_ciclo_completo_con_aprobacion():
    async def flujo():
        jobs = RepositorioFalso()
        worker = crear_worker(InMemorySaver(), jobs)
        await jobs.crear(JOB, "tarea")
        await worker._procesar("iniciar", JOB, {"tarea": "tarea", "simular_error": False})
        pausado = await jobs.obtener(JOB)
        await worker._procesar("reanudar", JOB, {"aprobado": True, "comentario": "ok"})
        return pausado, await jobs.obtener(JOB), worker.tracer.spans

    pausado, final, spans = asyncio.run(flujo())
    assert pausado["estado"] == EstadoJob.AWAITING_APPROVAL
    assert pausado["aprobacion_pendiente"]["accion"] == "revertir_despliegue"
    assert final["estado"] == EstadoJob.DONE
    assert final["resultado"]["flujo"] == ["investigador", "analista", "sintesis"]
    assert [nombre for nombre, _ in spans] == ["job.iniciar", "job.reanudar"]
    assert spans[0][1].atributos["session.id"] == JOB


def test_un_error_deja_el_job_en_failed():
    async def flujo():
        jobs = RepositorioFalso()
        worker = crear_worker(InMemorySaver(), jobs)
        await jobs.crear(JOB, "tarea")
        worker.iniciar()
        await worker.encolar_inicio(JOB, "tarea", simular_error=True)
        await worker.cola.join()
        await worker.detener()
        return await jobs.obtener(JOB)

    job = asyncio.run(flujo())
    assert job["estado"] == EstadoJob.FAILED
    assert "Error simulado" in job["error"]


def test_recupera_un_job_interrumpido_a_mitad_del_grafo():
    """El analista falla (como si el servidor cayera ahí). Un worker nuevo retoma desde el checkpoint."""

    async def flujo():
        checkpointer, jobs = InMemorySaver(), RepositorioFalso()
        await jobs.crear(JOB, "tarea")
        caido = crear_worker(checkpointer, jobs, accion="ninguna", fallas_analista=1)
        try:
            await caido._procesar("iniciar", JOB, {"tarea": "tarea", "simular_error": False})
        except ConnectionError:
            pass  # el job queda en RUNNING, como tras un reinicio
        assert (await jobs.obtener(JOB))["estado"] == EstadoJob.RUNNING

        nuevo = crear_worker(checkpointer, jobs, accion="ninguna")
        assert await nuevo.recuperar_pendientes() == 1
        tipo, job_id, datos = await nuevo.cola.get()
        assert tipo == "continuar"
        await nuevo._procesar(tipo, job_id, datos)
        return await jobs.obtener(JOB)

    job = asyncio.run(flujo())
    assert job["estado"] == EstadoJob.DONE
    assert job["resultado"]["flujo"] == ["investigador", "analista", "sintesis"]


def test_recupera_una_aprobacion_recibida_antes_del_reinicio():
    async def flujo():
        checkpointer, jobs = InMemorySaver(), RepositorioFalso()
        await jobs.crear(JOB, "tarea")
        await crear_worker(checkpointer, jobs)._procesar("iniciar", JOB, {"tarea": "tarea", "simular_error": False})
        # La API recibió la aprobación (PENDING + aprobacion) y el servidor se reinició antes de procesarla.
        await jobs.actualizar(JOB, EstadoJob.PENDING, aprobacion={"aprobado": True, "comentario": None})

        nuevo = crear_worker(checkpointer, jobs)
        await nuevo.recuperar_pendientes()
        tipo, job_id, datos = await nuevo.cola.get()
        await nuevo._procesar(tipo, job_id, datos)
        return tipo, await jobs.obtener(JOB)

    tipo, job = asyncio.run(flujo())
    assert tipo == "reanudar"
    assert job["estado"] == EstadoJob.DONE
    assert "APROBADA" in job["resultado"]["resultado_accion"]


async def esperar_estado_final(jobs, limite_s: float = 5) -> dict:
    for _ in range(int(limite_s / 0.05)):
        job = await jobs.obtener(JOB)
        if job["estado"] in (EstadoJob.DONE, EstadoJob.FAILED):
            return job
        await asyncio.sleep(0.05)
    raise TimeoutError("El job no terminó")


def test_error_transitorio_se_reintenta_desde_el_checkpoint():
    """El analista falla una vez con un error temporal: el job vuelve a PENDING y termina en DONE."""

    async def flujo():
        jobs = RepositorioFalso()
        grafo = ensamblar_grafo(nodos_completos(RedisFalso(), accion="ninguna", fallas_analista=1), InMemorySaver())
        worker = Worker(grafo, jobs, TracerFalso(), 1, 25, max_reintentos=2, espera_reintento_s=0)
        await jobs.crear(JOB, "tarea")
        worker.iniciar()
        await worker.encolar_inicio(JOB, "tarea")
        job = await esperar_estado_final(jobs)
        await worker.detener()
        return job, [nombre for nombre, _ in worker.tracer.spans]

    job, spans = asyncio.run(flujo())
    assert job["estado"] == EstadoJob.DONE
    assert job["reintentos"] == 1
    assert "Caída simulada" in job["ultimo_error"]
    assert spans == ["job.iniciar", "job.continuar"]  # el reintento continúa, no empieza de cero
    assert job["resultado"]["flujo"] == ["investigador", "analista", "sintesis"]


def test_agotados_los_reintentos_el_job_queda_en_failed():
    async def flujo():
        jobs = RepositorioFalso()
        grafo = ensamblar_grafo(nodos_completos(RedisFalso(), accion="ninguna", fallas_analista=5), InMemorySaver())
        worker = Worker(grafo, jobs, TracerFalso(), 1, 25, max_reintentos=2, espera_reintento_s=0)
        await jobs.crear(JOB, "tarea")
        worker.iniciar()
        await worker.encolar_inicio(JOB, "tarea")
        job = await esperar_estado_final(jobs)
        await worker.detener()
        return job

    job = asyncio.run(flujo())
    assert job["estado"] == EstadoJob.FAILED
    assert job["reintentos"] == 2


def test_clasificacion_de_errores():
    sobrecarga = RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand.")
    envuelto = ValueError("fallo del modelo")
    envuelto.__cause__ = sobrecarga
    assert es_transitorio(sobrecarga)
    assert es_transitorio(envuelto)
    assert es_transitorio(TimeoutError())
    assert not es_transitorio(RuntimeError("Error simulado para verificar el estado FAILED"))
    assert not es_transitorio(KeyError("siguiente"))
