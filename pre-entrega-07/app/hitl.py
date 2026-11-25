"""Human-in-the-loop: pausa el grafo antes de ejecutar una acción con efectos secundarios."""
import json
import time
import uuid
from typing import Literal

from langgraph.graph import END
from langgraph.types import interrupt
from redis.asyncio import Redis

from app.state import EstadoOrquestador

DESCRIPCIONES = {
    "revertir_despliegue": "Revertir el despliegue afectado (kestrel-cli desplegar revertir)",
    "congelar_despliegues": "Congelar los despliegues que no sean urgentes",
}
CLAVE_AUDITORIA = "auditoria:acciones"


def requiere_aprobacion(estado: EstadoOrquestador) -> Literal["aprobacion", "__end__"]:
    """Arista condicional: solo las acciones críticas pasan por la aprobación humana."""
    return "aprobacion" if estado.get("accion_critica", "ninguna") != "ninguna" else END


async def ejecutar_accion_critica(redis: Redis, accion: str, tarea: str, decision: dict) -> dict:
    """Simula la acción operativa y deja un registro de auditoría en Redis (el efecto secundario)."""
    registro = {"id": uuid.uuid4().hex[:12], "accion": accion, "tarea": tarea,
                "comentario_revisor": decision.get("comentario"), "ejecutada_en": time.time()}
    await redis.lpush(CLAVE_AUDITORIA, json.dumps(registro, ensure_ascii=False))
    return registro


def crear_nodo_aprobacion(redis: Redis):
    async def aprobacion(estado: EstadoOrquestador) -> dict:
        accion = estado["accion_critica"]
        # interrupt() detiene el grafo y guarda el checkpoint en Redis hasta recibir la decisión.
        decision = interrupt({
            "accion": accion,
            "descripcion": DESCRIPCIONES[accion],
            "justificacion": estado["justificacion_accion"],
            "como_responder": "POST /tasks/{job_id}/approve con {\"aprobado\": true o false}",
        })
        if not decision.get("aprobado"):
            return {"resultado_accion": f"Acción '{accion}' RECHAZADA por el revisor. "
                                        f"Comentario: {decision.get('comentario') or 'sin comentario'}"}
        registro = await ejecutar_accion_critica(redis, accion, estado["tarea"], decision)
        return {"resultado_accion": f"Acción '{accion}' APROBADA y ejecutada (simulada). "
                                    f"Registro de auditoría: {registro['id']}"}

    return aprobacion