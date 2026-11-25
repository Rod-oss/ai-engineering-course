"""Pruebas del sistema RAG: preguntas con respuesta y pregunta trampa."""
import asyncio
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

from rag import get_rag_response

PRUEBAS = [
    {
        "nombre": "respuesta_en_un_documento",
        "pregunta": "¿Qué se debe hacer si durante un despliegue canario la tasa de errores "
                    "supera el límite permitido?",
        "debe_encontrarse": True,
    },
    {
        "nombre": "respuesta_en_varios_documentos",
        "pregunta": "¿Qué base de datos usa el servicio de pedidos y qué severidad tiene un "
                    "incidente si esa base deja de aceptar escrituras?",
        "debe_encontrarse": True,
    },
    {
        "nombre": "pregunta_trampa",
        "pregunta": "¿Cuánto cuesta al mes el plan empresarial de la API de Kestrel?",
        "debe_encontrarse": False,
    },
]

ARCHIVO_EVIDENCIA = Path(__file__).resolve().parent / "resultados_pruebas.json"


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s | %(message)s")
    for ruidoso in ("httpx", "openai", "chromadb"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)

    resultados = await asyncio.gather(
        *(get_rag_response(prueba["pregunta"]) for prueba in PRUEBAS)
    )

    evidencia = []
    aprobadas = 0
    for prueba, resultado in zip(PRUEBAS, resultados):
        paso = resultado.encontrada == prueba["debe_encontrarse"]
        aprobadas += paso
        print(f"\n--- {prueba['nombre']}: {'PASÓ' if paso else 'FALLÓ'} ---")
        print(json.dumps(resultado.model_dump(), indent=2, ensure_ascii=False))
        evidencia.append({"prueba": prueba["nombre"], "paso": paso, **resultado.model_dump()})

    ARCHIVO_EVIDENCIA.write_text(json.dumps(evidencia, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{aprobadas}/{len(PRUEBAS)} pruebas aprobadas. Evidencia guardada en {ARCHIVO_EVIDENCIA.name}")


if __name__ == "__main__":
    asyncio.run(main())