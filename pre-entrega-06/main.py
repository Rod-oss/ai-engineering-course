"""Ejecuta el orquestador con la tarea de demostración y guarda la traza y el diagrama."""
import asyncio
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from config import RECURSION_LIMIT_GRAFO
from graph import construir_grafo, estado_inicial

BASE_DIR = Path(__file__).resolve().parent
TRAZA = BASE_DIR / "traza_orquestador.json"
DIAGRAMA = BASE_DIR / "grafo.mmd"

TAREA_DEMO = (
    "Este mes, de 30 días, Kestrel estuvo caído un total de 38 minutos. Además, durante un "
    "despliegue canario la tasa de errores llegó al 2,4 % durante 6 minutos consecutivos. "
    "¿Cumplimos el objetivo de disponibilidad mensual, qué porcentaje del presupuesto de error "
    "consumimos y qué acciones exige la documentación por el episodio del despliegue?"
)


def configurar_logs() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout, format="%(message)s")
    logging.getLogger("orquestador").setLevel(logging.INFO)


async def ejecutar(tarea: str) -> dict:
    grafo = construir_grafo()
    DIAGRAMA.write_text(grafo.get_graph().draw_mermaid(), encoding="utf-8")
    final = await grafo.ainvoke(estado_inicial(tarea), {"recursion_limit": RECURSION_LIMIT_GRAFO})
    traza = {
        "tarea": tarea,
        "pasos_supervisor": final["pasos_supervisor"],
        "decisiones": [d.model_dump() for d in final["decisiones"]],
        "contribuciones": [c.model_dump() for c in final["contribuciones"]],
        "respuesta_final": final["respuesta_final"],
    }
    TRAZA.write_text(json.dumps(traza, indent=2, ensure_ascii=False), encoding="utf-8")
    return traza


if __name__ == "__main__":
    load_dotenv()
    configurar_logs()
    traza = asyncio.run(ejecutar(TAREA_DEMO))
    ruta = " -> ".join(d["siguiente"] for d in traza["decisiones"])
    print(f"\nFlujo de delegación: supervisor -> {ruta}")
    print(f"Traza en {TRAZA.name}, diagrama en {DIAGRAMA.name}")