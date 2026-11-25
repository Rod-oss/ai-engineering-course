"""Recuperación híbrida: fusiona la búsqueda semántica y la léxica con Reciprocal Rank Fusion (RRF).

RRF suma, para cada fragmento, peso / (k + posición) en cada lista donde aparece. Premia los
fragmentos que ambos buscadores ubican arriba sin tener que comparar puntajes de escalas distintas
(coseno frente a BM25). Es el mismo criterio que usa EnsembleRetriever de LangChain (k = 60).
"""

from app.rag.lexico import BuscadorLexico
from app.rag.modelos import Fragmento
from app.rag.vectorial import BuscadorVectorial


def fusionar_rrf(listas: list[tuple[list[Fragmento], float]], k: int = 60) -> list[Fragmento]:
    """Combina listas ordenadas de fragmentos; elimina duplicados por chunk_id."""
    puntajes: dict[str, float] = {}
    fragmentos: dict[str, Fragmento] = {}
    for resultados, peso in listas:
        for posicion, fragmento in enumerate(resultados, start=1):
            puntajes[fragmento.chunk_id] = puntajes.get(fragmento.chunk_id, 0.0) + peso / (k + posicion)
            if fragmento.chunk_id in fragmentos:
                previo = fragmentos[fragmento.chunk_id]
                previo.metodos = sorted(set(previo.metodos) | set(fragmento.metodos))
            else:
                fragmentos[fragmento.chunk_id] = fragmento.model_copy()
    ordenados = sorted(puntajes, key=puntajes.get, reverse=True)
    return [fragmentos[c].model_copy(update={"puntaje": round(puntajes[c], 6)}) for c in ordenados]


class RecuperadorHibrido:
    def __init__(
        self,
        vectorial: BuscadorVectorial,
        lexico: BuscadorLexico,
        top_k: int,
        peso_vectorial: float = 0.5,
        rrf_k: int = 60,
    ) -> None:
        self.vectorial = vectorial
        self.lexico = lexico
        self.top_k = top_k
        self.peso_vectorial = peso_vectorial
        self.rrf_k = rrf_k

    async def buscar(self, consulta: str, categoria: str | None = None) -> list[Fragmento]:
        semanticos = await self.vectorial.buscar(consulta, self.top_k, categoria)
        lexicos = self.lexico.buscar(consulta, self.top_k, categoria)
        fusion = fusionar_rrf([(semanticos, self.peso_vectorial), (lexicos, 1 - self.peso_vectorial)], k=self.rrf_k)
        return fusion[: self.top_k]
