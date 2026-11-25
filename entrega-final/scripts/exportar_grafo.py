"""Exporta el diagrama del grafo de agentes a Mermaid, sin claves ni red.

    python scripts/exportar_grafo.py

Usa la misma topología que producción (ensamblar_grafo) con nodos vacíos, y escribe docs/grafo.mmd.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.graph.builder import NODOS, ensamblar_grafo  # noqa: E402


async def _nodo_vacio(estado: dict) -> dict:
    return {}


def main() -> None:
    grafo = ensamblar_grafo({nombre: _nodo_vacio for nombre in NODOS})
    mermaid = grafo.get_graph().draw_mermaid()
    destino = RAIZ / "docs" / "grafo.mmd"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(mermaid, encoding="utf-8")
    print(mermaid)
    print(f"Guardado en {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
