"""Dobles de prueba: nodos del grafo, Redis, repositorio de jobs y tracer, sin red ni claves."""

import copy
import time
from contextlib import contextmanager
from typing import Any

from app.graph.hitl import crear_nodo_aprobacion
from app.graph.state import Contribucion, Decision
from app.services.jobs import EstadoJob, RepositorioJobs

FLUJO = ["investigador", "analista", "sintesis"]


class RedisFalso:
    def __init__(self) -> None:
        self.listas: dict[str, list[str]] = {}

    async def lpush(self, nombre: str, *valores: str) -> int:
        self.listas.setdefault(nombre, [])[:0] = list(valores)
        return len(self.listas[nombre])

    async def ping(self) -> bool:
        return True


class RepositorioFalso(RepositorioJobs):
    """Misma interfaz que RepositorioJobs, pero en un diccionario."""

    def __init__(self) -> None:
        self.datos: dict[str, dict[str, Any]] = {}

    async def crear(self, job_id: str, tarea: str) -> None:
        ahora = time.time()
        self.datos[job_id] = {
            "job_id": job_id,
            "tarea": tarea,
            "estado": EstadoJob.PENDING,
            "creado": ahora,
            "actualizado": ahora,
        }

    async def actualizar(self, job_id: str, estado: EstadoJob, **campos: Any) -> None:
        self.datos[job_id].update(estado=estado, actualizado=time.time(), **copy.deepcopy(campos))

    async def borrar_campos(self, job_id: str, *campos: str) -> None:
        for campo in campos:
            self.datos[job_id].pop(campo, None)

    async def obtener(self, job_id: str) -> dict[str, Any] | None:
        job = copy.deepcopy(self.datos.get(job_id))
        if job and "fin" in job:
            job["duracion_total_s"] = round(job["fin"] - job["creado"], 2)
        return job

    async def ids(self):
        for job_id in list(self.datos):
            yield job_id


class SpanFalso:
    def __init__(self) -> None:
        self.atributos: dict[str, Any] = {}

    def set_attribute(self, clave: str, valor: Any) -> None:
        self.atributos[clave] = valor

    def set_status(self, *args, **kwargs) -> None:
        pass


class TracerFalso:
    def __init__(self) -> None:
        self.spans: list[tuple[str, SpanFalso]] = []

    @contextmanager
    def start_as_current_span(self, nombre: str, **kwargs):
        span = SpanFalso()
        self.spans.append((nombre, span))
        yield span


def crear_nodos_falsos(accion: str = "revertir_despliegue", fallas_analista: int = 0) -> dict:
    """Nodos que reproducen el flujo supervisor -> investigador -> analista -> síntesis sin LLM.

    `fallas_analista` hace que el analista falle esas veces (simula una caída a mitad del grafo)."""
    contador = {"fallas": fallas_analista}

    async def supervisor(estado: dict) -> dict:
        paso = estado["pasos_supervisor"] + 1
        siguiente = FLUJO[min(paso - 1, 2)]
        decision = Decision(paso=paso, siguiente=siguiente, instruccion=f"paso {paso}", evaluacion="ok")
        return {
            "siguiente": siguiente,
            "instruccion": decision.instruccion,
            "pasos_supervisor": paso,
            "decisiones": [decision.model_dump()],
        }

    def especialista(nombre: str):
        async def nodo(estado: dict) -> dict:
            if nombre == "analista" and contador["fallas"] > 0:
                contador["fallas"] -= 1
                raise ConnectionError("Caída simulada del proveedor")
            aporte = Contribucion(
                paso=estado["pasos_supervisor"],
                agente=nombre,
                instruccion=estado["instruccion"],
                resultado=f"resultado de {nombre}",
            )
            return {"contribuciones": [aporte.model_dump()]}

        return nodo

    async def sintesis(estado: dict) -> dict:
        return {
            "respuesta_final": "respuesta final",
            "accion_critica": accion,
            "justificacion_accion": "2,4 % > 2 % durante más de 5 minutos" if accion != "ninguna" else "",
        }

    return {
        "supervisor": supervisor,
        "investigador": especialista("investigador"),
        "analista": especialista("analista"),
        "sintesis": sintesis,
    }


def nodos_completos(redis: RedisFalso, **kwargs) -> dict:
    return {**crear_nodos_falsos(**kwargs), "aprobacion": crear_nodo_aprobacion(redis)}
