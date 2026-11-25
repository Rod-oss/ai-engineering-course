"""Mini-script de prueba asíncrono del pipeline de extracción."""
import asyncio
import json
import logging

from dotenv import load_dotenv

from chain import PipelineError, construir_cadena, process_text

CASOS = {
    "log_error": (
        "2026-11-24 03:12:44 ERROR [payments-api] psycopg.OperationalError: connection to "
        "server at 'db-prod' (PostgreSQL 16) failed: too many clients already. Los workers "
        "de FastAPI devuelven 503 y la cola de Celery en Redis acumula 12.000 tareas "
        "pendientes. Los pagos de los clientes están fallando en producción."
    ),
    "arquitectura": (
        "Nuestro frontend en React consume una API GraphQL escrita en Node.js con Apollo "
        "Server. Los datos viven en MongoDB Atlas y las imágenes se sirven desde Amazon S3 "
        "con CloudFront. Estamos evaluando migrar los trabajos programados a AWS Lambda "
        "para reducir costos."
    ),
    "ambiguo": (
        "Desde ayer la app va lenta a ratos. Puede ser la base de datos, la red o algo del "
        "último despliegue; nadie está seguro y no hay errores claros en los registros."
    ),
}


def mostrar(etiqueta: str, resultado: object) -> None:
    print(f"\n--- {etiqueta} ---")
    if isinstance(resultado, Exception):
        print(f"Error controlado: {resultado}")
    else:
        print(json.dumps(resultado.model_dump(mode="json"), indent=2, ensure_ascii=False))


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, datefmt="%H:%M:%S",
                        format="%(asctime)s %(levelname)-7s %(message)s")
    for ruidoso in ("httpx", "openai", "langchain"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)

    print("\n=== Casos 1 a 3 en paralelo ===")
    resultados = await asyncio.gather(
        *(process_text(texto, etiqueta=etiqueta) for etiqueta, texto in CASOS.items()),
        return_exceptions=True,
    )
    for etiqueta, resultado in zip(CASOS, resultados):
        mostrar(etiqueta, resultado)

    print("\n=== Caso 4: límite de tokens muy bajo (fuerza finish_reason=length) ===")
    cadena_limitada = construir_cadena(max_tokens=30)
    try:
        resultado = await process_text(CASOS["log_error"], cadena=cadena_limitada,
                                       etiqueta="tokens_insuficientes")
        mostrar("tokens_insuficientes", resultado)
    except PipelineError as err:
        mostrar("tokens_insuficientes", err)


if __name__ == "__main__":
    asyncio.run(main())