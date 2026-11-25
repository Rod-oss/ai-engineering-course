"""Estado de los jobs en Redis: PENDING, RUNNING, AWAITING_APPROVAL, DONE o FAILED."""

import json
import time
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any

from redis.asyncio import Redis

PREFIJO = "job:"
CAMPOS_JSON = {"resultado", "aprobacion_pendiente", "aprobacion"}
CAMPOS_NUMERICOS = {"creado", "actualizado", "inicio", "fin"}


class EstadoJob(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    DONE = "DONE"
    FAILED = "FAILED"


def _a_redis(valor: Any) -> str | int | float:
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
        return json.dumps(valor, ensure_ascii=False)
    return valor


class RepositorioJobs:
    def __init__(self, redis: Redis, ttl_segundos: int) -> None:
        self.redis = redis
        self.ttl_segundos = ttl_segundos

    async def crear(self, job_id: str, tarea: str) -> None:
        ahora = time.time()
        clave = PREFIJO + job_id
        await self.redis.hset(
            clave,
            mapping={
                "job_id": job_id,
                "tarea": tarea,
                "estado": EstadoJob.PENDING,
                "creado": ahora,
                "actualizado": ahora,
            },
        )
        await self.redis.expire(clave, self.ttl_segundos)

    async def actualizar(self, job_id: str, estado: EstadoJob, **campos: Any) -> None:
        datos = {"estado": estado, "actualizado": time.time()}
        datos.update({k: _a_redis(v) for k, v in campos.items()})
        await self.redis.hset(PREFIJO + job_id, mapping=datos)

    async def borrar_campos(self, job_id: str, *campos: str) -> None:
        await self.redis.hdel(PREFIJO + job_id, *campos)

    async def obtener(self, job_id: str) -> dict[str, Any] | None:
        datos = await self.redis.hgetall(PREFIJO + job_id)
        if not datos:
            return None
        for campo in CAMPOS_JSON & datos.keys():
            datos[campo] = json.loads(datos[campo])
        for campo in CAMPOS_NUMERICOS & datos.keys():
            datos[campo] = float(datos[campo])
        if "fin" in datos:
            datos["duracion_total_s"] = round(datos["fin"] - datos["creado"], 2)
        return datos

    async def ids(self) -> AsyncIterator[str]:
        """Recorre todos los jobs guardados (SCAN no bloquea Redis como KEYS)."""
        async for clave in self.redis.scan_iter(match=PREFIJO + "*", count=200):
            yield clave.removeprefix(PREFIJO)
