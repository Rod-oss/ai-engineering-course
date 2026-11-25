"""Recuperación híbrida: BM25, fusión RRF y combinación con un buscador vectorial falso."""

import asyncio

from langchain_core.documents import Document

from app.rag.hibrido import RecuperadorHibrido, fusionar_rrf
from app.rag.lexico import BuscadorLexico, tokenizar
from app.rag.modelos import Fragmento


def fragmento(chunk_id: str, metodo: str = "vectorial") -> Fragmento:
    return Fragmento(chunk_id=chunk_id, fuente=f"{chunk_id}.md", categoria="procesos", texto="...", metodos=[metodo])


DOCUMENTOS = [
    Document(
        page_content="Revertir el despliegue si la tasa de errores supera el 2 % durante 5 minutos.",
        metadata={"chunk_id": "despliegues-00", "source": "despliegues.md", "categoria": "procesos"},
    ),
    Document(
        page_content="El comando kestrel-cli db restaurar recupera un respaldo.",
        metadata={"chunk_id": "datos-00", "source": "datos.md", "categoria": "operaciones"},
    ),
    Document(
        page_content="Las vulnerabilidades críticas se corrigen en 72 horas.",
        metadata={"chunk_id": "seguridad-00", "source": "seguridad.md", "categoria": "seguridad"},
    ),
]


def test_tokenizar_conserva_terminos_tecnicos():
    assert "kestrel-cli" in tokenizar("Usa kestrel-cli para restaurar")
    assert "pedidos.muertos" in tokenizar("La cola pedidos.muertos crece")


def test_bm25_encuentra_coincidencias_exactas():
    resultados = BuscadorLexico(DOCUMENTOS).buscar("kestrel-cli db restaurar", k=2)
    assert resultados[0].chunk_id == "datos-00"
    assert resultados[0].metodos == ["lexico"]


def test_bm25_respeta_el_filtro_de_categoria():
    resultados = BuscadorLexico(DOCUMENTOS).buscar("errores despliegue respaldo", k=3, categoria="operaciones")
    assert {r.categoria for r in resultados} == {"operaciones"}


def test_rrf_premia_lo_que_ambos_buscadores_encuentran():
    vectorial = [fragmento("a"), fragmento("b"), fragmento("c")]
    lexico = [fragmento("c", "lexico"), fragmento("d", "lexico")]
    fusion = fusionar_rrf([(vectorial, 0.5), (lexico, 0.5)])
    ids = [f.chunk_id for f in fusion]
    assert ids[0] == "c"  # aparece en ambas listas
    assert len(ids) == len(set(ids)) == 4  # sin duplicados
    assert fusion[0].metodos == ["lexico", "vectorial"]


def test_rrf_respeta_los_pesos():
    fusion = fusionar_rrf([([fragmento("a")], 0.9), ([fragmento("b", "lexico")], 0.1)])
    assert [f.chunk_id for f in fusion] == ["a", "b"]


class VectorialFalso:
    async def buscar(self, consulta: str, k: int, categoria: str | None = None) -> list[Fragmento]:
        return [fragmento("despliegues-00"), fragmento("seguridad-00")][:k]


def test_recuperador_hibrido_combina_y_recorta_a_top_k():
    recuperador = RecuperadorHibrido(VectorialFalso(), BuscadorLexico(DOCUMENTOS), top_k=2)
    resultados = asyncio.run(recuperador.buscar("tasa de errores del despliegue"))
    assert len(resultados) == 2
    assert resultados[0].chunk_id == "despliegues-00"
    assert set(resultados[0].metodos) == {"vectorial", "lexico"}
