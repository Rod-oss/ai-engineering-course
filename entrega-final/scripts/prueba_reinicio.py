"""Prueba de persistencia: reinicia la API a mitad de los jobs y comprueba que nada se pierde.

Uso (con el sistema levantado con Docker Compose):
    python scripts/prueba_reinicio.py

Escenario 1, pausa HITL: un job llega a AWAITING_APPROVAL, se reinicia la API, se consulta el
checkpoint (sigue pausado en el nodo de aprobación) y se aprueba. Debe terminar en DONE.

Escenario 2, a mitad del grafo: un job está en RUNNING, se reinicia la API y, al arrancar, el
worker lo retoma desde su último checkpoint. Debe terminar en DONE sin repetir los pasos ya hechos.

Si la API no corre en Docker, usa --manual: el script se detiene y te pide reiniciarla a mano.
Guarda los resultados en resultados/reinicio.json.
"""

import argparse
import asyncio
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "resultados" / "reinicio.json"
TAREA_HITL = (
    "Durante un despliegue canario la tasa de errores llegó al 2,4 % durante 6 minutos consecutivos. "
    "¿Qué exige la documentación?"
)
TAREA_LARGA = (
    "Este mes acumulamos 12 minutos de indisponibilidad. ¿Cuánto presupuesto de error nos queda según el SLO "
    "documentado y qué indica la documentación si se agota?"
)


async def esperar_estado(cliente: httpx.AsyncClient, job_id: str, estados: set[str], limite_s: float = 600) -> dict:
    inicio = time.perf_counter()
    while time.perf_counter() - inicio < limite_s:
        try:
            job = (await cliente.get(f"/tasks/{job_id}")).json()
            if job.get("estado") in estados:
                return job
            if job.get("estado") == "FAILED":
                raise RuntimeError(f"El job {job_id} falló: {job.get('error')}")
        except httpx.TransportError:
            pass  # la API se está reiniciando
        await asyncio.sleep(2)
    raise TimeoutError(f"El job {job_id} no llegó a {estados} en {limite_s} s")


async def esperar_api(cliente: httpx.AsyncClient, limite_s: float = 120) -> None:
    inicio = time.perf_counter()
    while time.perf_counter() - inicio < limite_s:
        try:
            if (await cliente.get("/health")).status_code == 200:
                return
        except httpx.TransportError:
            pass
        await asyncio.sleep(2)
    raise TimeoutError("La API no volvió a responder")


async def reiniciar_api(cliente: httpx.AsyncClient, manual: bool) -> float:
    print("  -> Reiniciando la API...")
    inicio = time.perf_counter()
    if manual:
        await asyncio.to_thread(input, "     Reinicia la API (Ctrl + C y vuelve a lanzar uvicorn) y presiona Enter: ")
    else:
        await asyncio.to_thread(subprocess.run, ["docker", "compose", "restart", "api"], cwd=RAIZ, check=True)
    await esperar_api(cliente)
    segundos = round(time.perf_counter() - inicio, 1)
    print(f"  -> API disponible de nuevo tras {segundos} s")
    return segundos


async def crear(cliente: httpx.AsyncClient, tarea: str) -> str:
    respuesta = await cliente.post("/tasks", json={"tarea": tarea})
    respuesta.raise_for_status()
    return respuesta.json()["job_id"]


async def escenario_hitl(cliente: httpx.AsyncClient, manual: bool) -> dict:
    print("\nEscenario 1: reinicio mientras un job espera aprobación humana")
    job_id = await crear(cliente, TAREA_HITL)
    job = await esperar_estado(cliente, job_id, {"AWAITING_APPROVAL", "DONE"})
    if job["estado"] == "DONE":
        print("  El modelo no propuso acción crítica esta vez; el escenario no aplica.")
        return {"job_id": job_id, "aplica": False}
    print(f"  [{job_id[:8]}] en AWAITING_APPROVAL: {job['aprobacion_pendiente']['accion']}")
    antes = (await cliente.get(f"/tasks/{job_id}/checkpoint")).json()
    segundos = await reiniciar_api(cliente, manual)
    despues = (await cliente.get(f"/tasks/{job_id}/checkpoint")).json()
    print(
        f"  Checkpoint tras el reinicio: siguiente nodo {despues['siguiente_nodo']}, decisiones {despues['decisiones']}"
    )
    await cliente.post(f"/tasks/{job_id}/approve", json={"aprobado": True, "comentario": "Aprobado tras el reinicio"})
    final = await esperar_estado(cliente, job_id, {"DONE"})
    print(f"  [{job_id[:8]}] {final['estado']}: {final['resultado']['resultado_accion']}")
    return {
        "job_id": job_id,
        "aplica": True,
        "reinicio_s": segundos,
        "checkpoint_antes": antes,
        "checkpoint_despues": despues,
        "mismo_checkpoint": antes["checkpoint_id"] == despues["checkpoint_id"],
        "estado_final": final["estado"],
        "resultado_accion": final["resultado"]["resultado_accion"],
    }


async def escenario_mitad(cliente: httpx.AsyncClient, manual: bool) -> dict:
    print("\nEscenario 2: reinicio mientras un job se está ejecutando")
    job_id = await crear(cliente, TAREA_LARGA)
    await esperar_estado(cliente, job_id, {"RUNNING"})
    await asyncio.sleep(8)  # deja que el grafo avance algunos pasos
    antes = (await cliente.get(f"/tasks/{job_id}/checkpoint")).json()
    print(f"  [{job_id[:8]}] en RUNNING; pasos hechos antes del reinicio: {antes['decisiones']}")
    segundos = await reiniciar_api(cliente, manual)
    final = await esperar_estado(cliente, job_id, {"DONE", "AWAITING_APPROVAL"})
    if final["estado"] == "AWAITING_APPROVAL":
        await cliente.post(f"/tasks/{job_id}/approve", json={"aprobado": True, "comentario": "Prueba de reinicio"})
        final = await esperar_estado(cliente, job_id, {"DONE"})
    print(f"  [{job_id[:8]}] {final['estado']} tras el reinicio; flujo completo: {final['resultado']['flujo']}")
    return {
        "job_id": job_id,
        "reinicio_s": segundos,
        "decisiones_antes_del_reinicio": antes["decisiones"],
        "flujo_final": final["resultado"]["flujo"],
        "estado_final": final["estado"],
    }


async def main(url: str, manual: bool) -> None:
    async with httpx.AsyncClient(base_url=url, timeout=30) as cliente:
        await esperar_api(cliente)
        resultados = {
            "fecha_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "hitl": await escenario_hitl(cliente, manual),
            "mitad_del_grafo": await escenario_mitad(cliente, manual),
        }
    ARCHIVO.parent.mkdir(exist_ok=True)
    ARCHIVO.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResultados guardados en resultados/{ARCHIVO.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prueba de persistencia ante reinicios")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--manual", action="store_true", help="Reiniciar la API a mano en lugar de con Docker")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.manual))
