"""Evaluación de la recuperación: Recall@k y Precision@k sobre un golden set."""
import asyncio
import json
import logging
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from rag_system import MODOS, RAGSystem

BASE_DIR = Path(__file__).resolve().parent
GOLDEN_SET = BASE_DIR / "golden_set.json"
RESULTADOS = BASE_DIR / "resultados_evaluacion.json"


def evaluar_pregunta(item: dict, fuentes: list[str], k: int, fragmentos_por_doc: Counter) -> dict:
    relevantes = set(item.get("documentos_relevantes", [item["documento_id_esperado"]]))
    aciertos = sum(fuente in relevantes for fuente in fuentes)
    posicion = next((i + 1 for i, f in enumerate(fuentes) if f == item["documento_id_esperado"]), None)
    maximo = min(sum(fragmentos_por_doc[d] for d in relevantes), k)
    return {
        "id": item["id"],
        "tipo": item["tipo"],
        "recall": 1.0 if posicion else 0.0,       # ¿apareció el documento esperado?
        "precision": aciertos / k,                # proporción de los k que son relevantes
        "precision_maxima": maximo / k,           # techo según cuántos fragmentos relevantes existen
        "posicion": posicion,
        "recuperados": fuentes,
    }


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.WARNING)
    golden = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    rag = RAGSystem()
    fragmentos_por_doc = Counter(f.metadata["source"] for f in rag.fragmentos)

    resultados = {}
    for modo in MODOS:
        # En secuencia: el cliente asíncrono de langchain-pinecone falla con búsquedas concurrentes.
        busquedas = []
        for item in golden:
            busquedas.append(await rag.abuscar(item["pregunta"], modo=modo))
        resultados[modo] = [
            evaluar_pregunta(item, [d.metadata["source"] for d in docs], rag.k, fragmentos_por_doc)
            for item, docs in zip(golden, busquedas)
        ]

    print(f"\nEvaluación con k={rag.k} sobre {len(golden)} preguntas "
          f"({len(rag.fragmentos)} fragmentos indexados)\n")
    print(f"{'Pregunta':<6}{'Tipo':<16}" + "".join(f"{m:>22}" for m in MODOS))
    print(f"{'':<22}" + "".join(f"{'R@5  P@5  posición':>22}" for _ in MODOS))
    for i, item in enumerate(golden):
        celdas = ""
        for modo in MODOS:
            r = resultados[modo][i]
            celdas += f"{r['recall']:>9.0f}{r['precision']:>5.2f}{str(r['posicion'] or '-'):>8}"
        print(f"{item['id']:<6}{item['tipo']:<16}{celdas}")

    print("\nResumen")
    resumen = {}
    for modo in MODOS:
        filas = resultados[modo]
        recall = sum(r["recall"] for r in filas) / len(filas)
        precision = sum(r["precision"] for r in filas) / len(filas)
        techo = sum(r["precision_maxima"] for r in filas) / len(filas)
        resumen[modo] = {"recall_at_5": recall, "precision_at_5": precision, "precision_maxima": techo}
        print(f"  {modo:<10} Recall@5 = {recall:.2f}   Precision@5 = {precision:.2f}   "
              f"(máxima posible: {techo:.2f})")

    RESULTADOS.write_text(
        json.dumps({"resumen": resumen, "detalle": resultados}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nDetalle guardado en {RESULTADOS.name}")


if __name__ == "__main__":
    asyncio.run(main())