"""Prueba del agente: razonamiento multi-paso, persistencia, ambigüedad y errores."""
import asyncio
import json
import logging

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent import construir_grafo, ejecutar_turno
from config import BASE_DIR

DB_DEMO = BASE_DIR / "demo_checkpoints.sqlite"
TRAZA_JSON = BASE_DIR / "traza_react.json"
TRAZA_LOG = BASE_DIR / "traza_react.log"
PAUSA_ENTRE_TURNOS = 5  # segundos, para respetar el límite de peticiones por minuto del plan gratuito

# Cada bloque se ejecuta con una conexión NUEVA a SQLite, como si el programa se reiniciara.
BLOQUES = [
    [
        ("sesion-mariana", "¿Cuántos pedidos tuvo la clienta Mariana Lopes y cuál fue el total?"),
    ],
    [
        ("sesion-mariana", "¿Y el último? ¿Qué productos incluía y en qué estado está?"),
        ("sesion-nueva", "¿Y el último? ¿Qué productos incluía?"),
        ("sesion-ana", "¿Cuánto ha gastado Ana en total?"),
        ("sesion-ana", "Me refiero a Ana Ruiz."),
        ("sesion-error", "Dame el resumen de pedidos del cliente con id 999."),
    ],
]


def configurar_logs() -> None:
    formato = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for handler in (logging.StreamHandler(), logging.FileHandler(TRAZA_LOG, mode="w", encoding="utf-8")):
        handler.setFormatter(formato)
        logging.getLogger("agente").addHandler(handler)
    logging.getLogger("agente").setLevel(logging.INFO)


async def main() -> None:
    load_dotenv()
    configurar_logs()
    DB_DEMO.unlink(missing_ok=True)  # la demo empieza siempre sin historial
    traza: list[dict] = []

    for numero, bloque in enumerate(BLOQUES, start=1):
        logging.getLogger("agente").info("===== Conexión %d a SQLite (%s) =====", numero, DB_DEMO.name)
        async with AsyncSqliteSaver.from_conn_string(str(DB_DEMO)) as checkpointer:
            grafo = construir_grafo(checkpointer)
            for thread_id, mensaje in bloque:
                respuesta, pasos = await ejecutar_turno(grafo, thread_id, mensaje)
                usadas = sum(len(p["herramientas"]) for p in pasos if p["tipo"] == "accion")
                estado = await grafo.aget_state({"configurable": {"thread_id": thread_id}})
                traza.append({
                    "conexion_sqlite": numero,
                    "thread_id": thread_id,
                    "usuario": mensaje,
                    "pasos": pasos,
                    "respuesta": respuesta,
                    "herramientas_en_el_turno": usadas,
                    "herramientas_en_la_sesion": estado.values.get("llamadas_herramientas", 0),
                    "mensajes_en_el_historial": len(estado.values.get("messages", [])),
                })
                await asyncio.sleep(PAUSA_ENTRE_TURNOS)

    TRAZA_JSON.write_text(json.dumps(traza, indent=2, ensure_ascii=False), encoding="utf-8")

    primero = traza[0]
    print("\n===== Verificación =====")
    print(f"Multi-paso: el primer turno usó {primero['herramientas_en_el_turno']} herramientas "
          f"({'cumple' if primero['herramientas_en_el_turno'] >= 2 else 'NO cumple'} el mínimo de 2)")
    print(f"Traza guardada en {TRAZA_JSON.name} y {TRAZA_LOG.name}")


if __name__ == "__main__":
    asyncio.run(main())