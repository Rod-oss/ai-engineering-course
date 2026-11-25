"""API: validación de entradas (422), contrato de salida y códigos 202, 404 y 409."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.api.routes import router
from app.graph.builder import ensamblar_grafo
from app.services.jobs import EstadoJob
from tests.fakes import RedisFalso, RepositorioFalso, nodos_completos

TAREA = {"tarea": "La tasa de errores llegó al 2,4 % durante 6 minutos. ¿Qué exige la documentación?"}


class WorkerFalso:
    def __init__(self) -> None:
        self.encolados: list[tuple] = []
        self.en_cola = 0

    async def encolar_inicio(self, job_id, tarea, simular_error=False):
        self.encolados.append(("iniciar", job_id))

    async def encolar_reanudacion(self, job_id, decision):
        self.encolados.append(("reanudar", job_id, decision))


@pytest.fixture
def cliente():
    app = FastAPI()
    app.include_router(router)
    app.state.redis, app.state.jobs, app.state.worker = RedisFalso(), RepositorioFalso(), WorkerFalso()
    app.state.grafo = ensamblar_grafo(nodos_completos(RedisFalso()), InMemorySaver())
    return TestClient(app)


def test_health(cliente):
    assert cliente.get("/health").json() == {"api": "ok", "redis": True, "jobs_en_cola": 0}


def test_crear_tarea_responde_202_con_job_id(cliente):
    respuesta = cliente.post("/tasks", json=TAREA)
    assert respuesta.status_code == 202
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "PENDING" and len(cuerpo["job_id"]) == 32
    assert cliente.get(cuerpo["consultar"]).json()["estado"] == "PENDING"


@pytest.mark.parametrize("cuerpo", [{"tarea": "corta"}, {"tarea": "x" * 2001}, {**TAREA, "campo_extra": 1}, {}])
def test_entradas_invalidas_responden_422(cliente, cuerpo):
    assert cliente.post("/tasks", json=cuerpo).status_code == 422


def test_job_id_invalido_o_inexistente(cliente):
    assert cliente.get("/tasks/no-es-un-id").status_code == 422
    assert cliente.get("/tasks/" + "0" * 32).status_code == 404


def test_aprobar_un_job_que_no_espera_aprobacion_responde_409(cliente):
    job_id = cliente.post("/tasks", json=TAREA).json()["job_id"]
    assert cliente.post(f"/tasks/{job_id}/approve", json={"aprobado": True}).status_code == 409


def test_aprobacion_valida_el_cuerpo_y_encola_la_reanudacion(cliente):
    job_id = cliente.post("/tasks", json=TAREA).json()["job_id"]
    jobs = cliente.app.state.jobs
    jobs.datos[job_id]["estado"] = EstadoJob.AWAITING_APPROVAL
    assert cliente.post(f"/tasks/{job_id}/approve", json={"aprobado": "quizas"}).status_code == 422
    respuesta = cliente.post(f"/tasks/{job_id}/approve", json={"aprobado": True, "comentario": "ok"})
    assert respuesta.status_code == 202
    assert cliente.app.state.worker.encolados[-1] == ("reanudar", job_id, {"aprobado": True, "comentario": "ok"})


def test_la_documentacion_openapi_incluye_todos_los_endpoints(cliente):
    rutas = cliente.get("/openapi.json").json()["paths"]
    assert {
        "/health",
        "/tasks",
        "/tasks/{job_id}",
        "/tasks/{job_id}/approve",
        "/tasks/{job_id}/checkpoint",
    } <= rutas.keys()
