"""Prueba de carga: 5 solicitudes concurrentes contra la API del orquestador.

Uso:
    python scripts/load_test.py
    python scripts/load_test.py --url http://localhost:8000

Qué hace:
1. Envía las 5 tareas a POST /tasks al mismo tiempo.
2. Consulta el estado de cada job cada pocos segundos.
3. Si un job queda en AWAITING_APPROVAL, lo aprueba (revisor simulado).
4. Calcula la latencia de extremo a extremo (p50, p95, máx.) y guarda resultados/carga.json.
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

TAREAS = [
    "Durante un despliegue canario la tasa de errores llegó al 2,4 % durante 6 minutos consecutivos. ¿Qué exige la documentación?",
    "Un despliegue canario lleva 10 minutos con una tasa de errores del 1,6 % y una latencia p95 de 950 ms. ¿Qué indica la documentación?",
    "Este mes acumulamos 12 minutos de indisponibilidad. ¿Cuánto presupuesto de error nos queda según el SLO documentado?",
    "Se detectó una vulnerabilidad con CVSS 9,3 hace 50 horas. ¿Qué plazo de corrección exige la documentación y cuánto tiempo queda?",
    "En el último simulacro de recuperación el servicio tardó 41 minutos en restablecerse. ¿Cumple con el RTO documentado?",
]
INTERVALO_SONDEO_S = 3
TIEMPO_MAXIMO_S = 900
ESTADOS_FINALES = {"DONE", "FAILED"}
ARCHIVO_RESULTADOS = Path(__file__).resolve().parent.parent / "resultados" / "carga.json"


def percentil(valores: list[float], p: float) -> float:
    """Percentil con interpolación lineal (el mismo método que numpy usa por defecto)."""
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    posicion = (len(ordenados) - 1) * p / 100
    inferior = int(posicion)
    superior = min(inferior + 1, len(ordenados) - 1)
    fraccion = posicion - inferior
    return ordenados[inferior] + (ordenados[superior] - ordenados[inferior]) * fraccion


async def enviar(cliente: httpx.AsyncClient, tarea: str) -> dict:
    """Envía una tarea y mide cuánto tarda la API en responder el 202."""
    inicio = time.perf_counter()
    respuesta = await cliente.post("/tasks", json={"tarea": tarea})
    respuesta.raise_for_status()
    return {
        "job_id": respuesta.json()["job_id"],
        "tarea": tarea,
        "inicio": inicio,
        "respuesta_post_ms": round((time.perf_counter() - inicio) * 1000, 1),
    }


async def seguir_job(cliente: httpx.AsyncClient, envio: dict) -> dict:
    """Consulta el job hasta que termina; si pide aprobación, la concede."""
    job_id, inicio = envio["job_id"], envio["inicio"]
    aprobado = False
    while True:
        transcurrido = time.perf_counter() - inicio
        if transcurrido > TIEMPO_MAXIMO_S:
            return {**_base(envio), "estado": "TIMEOUT", "latencia_s": round(transcurrido, 2)}

        respuesta = await cliente.get(f"/tasks/{job_id}")
        respuesta.raise_for_status()
        job = respuesta.json()
        estado = job["estado"]

        if estado == "AWAITING_APPROVAL" and not aprobado:
            await cliente.post(
                f"/tasks/{job_id}/approve",
                json={"aprobado": True, "comentario": "Aprobación automática de la prueba de carga"},
            )
            aprobado = True
            print(f"  [{job_id[:8]}] pidió aprobación: aprobado por el revisor simulado")
        elif estado in ESTADOS_FINALES:
            latencia = round(time.perf_counter() - inicio, 2)
            resultado = job.get("resultado") or {}
            print(f"  [{job_id[:8]}] terminó en {estado} tras {latencia} s")
            return {
                **_base(envio),
                "estado": estado,
                "latencia_s": latencia,
                "duracion_servidor_s": job.get("duracion_total_s"),
                "requirio_aprobacion": aprobado,
                "accion_critica": resultado.get("accion_critica"),
                "resultado_accion": resultado.get("resultado_accion"),
                "flujo": resultado.get("flujo"),
                "error": job.get("error"),
            }
        await asyncio.sleep(INTERVALO_SONDEO_S)


def _base(envio: dict) -> dict:
    return {"job_id": envio["job_id"], "tarea": envio["tarea"], "respuesta_post_ms": envio["respuesta_post_ms"]}


async def main(url: str) -> None:
    async with httpx.AsyncClient(base_url=url, timeout=30) as cliente:
        (await cliente.get("/health")).raise_for_status()
        print(f"Enviando {len(TAREAS)} solicitudes concurrentes a {url}\n")
        inicio_global = time.perf_counter()

        envios = await asyncio.gather(*(enviar(cliente, tarea) for tarea in TAREAS))
        for envio in envios:
            print(f"  202 en {envio['respuesta_post_ms']:.0f} ms -> {envio['job_id']}")
        print("\nEsperando resultados (puede tardar varios minutos por el límite de Gemini)...\n")

        resultados = await asyncio.gather(*(seguir_job(cliente, envio) for envio in envios))
        duracion_total = round(time.perf_counter() - inicio_global, 2)

    completados = [r for r in resultados if r["estado"] == "DONE"]
    latencias = [r["latencia_s"] for r in completados]
    tiempos_post = [r["respuesta_post_ms"] for r in resultados]
    resumen = {
        "fecha_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "url": url,
        "solicitudes": len(resultados),
        "completadas": len(completados),
        "fallidas": sum(r["estado"] == "FAILED" for r in resultados),
        "timeout": sum(r["estado"] == "TIMEOUT" for r in resultados),
        "con_aprobacion_hitl": sum(r.get("requirio_aprobacion", False) for r in resultados),
        "duracion_total_prueba_s": duracion_total,
        "latencia_extremo_a_extremo_s": {
            "p50": round(percentil(latencias, 50), 2),
            "p95": round(percentil(latencias, 95), 2),
            "max": max(latencias),
        }
        if latencias
        else None,
        "respuesta_post_ms": {
            "p50": round(percentil(tiempos_post, 50), 1),
            "p95": round(percentil(tiempos_post, 95), 1),
        },
        "nota": "Latencia medida desde el cliente: incluye la espera en cola (concurrencia del worker = 2) "
        "y hasta 3 s de margen por el intervalo de sondeo.",
    }

    ARCHIVO_RESULTADOS.parent.mkdir(exist_ok=True)
    ARCHIVO_RESULTADOS.write_text(
        json.dumps({"resumen": resumen, "jobs": resultados}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== Resumen ===")
    print(
        f"Completadas: {resumen['completadas']}/{resumen['solicitudes']} "
        f"| Fallidas: {resumen['fallidas']} | Timeout: {resumen['timeout']} "
        f"| Con aprobación HITL: {resumen['con_aprobacion_hitl']}"
    )
    if latencias:
        lat = resumen["latencia_extremo_a_extremo_s"]
        print(f"Latencia de extremo a extremo: p50 {lat['p50']} s | p95 {lat['p95']} s | máx. {lat['max']} s")
    print(
        f"Respuesta del POST /tasks: p50 {resumen['respuesta_post_ms']['p50']} ms "
        f"| p95 {resumen['respuesta_post_ms']['p95']} ms"
    )
    print(f"Duración total de la prueba: {duracion_total} s")
    print(f"Resultados guardados en resultados/{ARCHIVO_RESULTADOS.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prueba de carga de la API del orquestador")
    parser.add_argument("--url", default="http://localhost:8000")
    asyncio.run(main(parser.parse_args().url))
