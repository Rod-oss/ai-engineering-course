"""Topología del grafo, aprobación humana y persistencia con checkpointer (en memoria para la prueba)."""

import asyncio
import json

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graph.builder import ensamblar_grafo
from app.graph.hitl import CLAVE_AUDITORIA
from app.graph.state import Contribucion, a_modelo, contribuciones, estado_inicial
from tests.fakes import RedisFalso, nodos_completos

CONFIG = {"configurable": {"thread_id": "prueba"}}


def test_a_modelo_acepta_objeto_dict_y_formato_langchain():
    datos = {"paso": 1, "agente": "analista", "instruccion": "i", "resultado": "r", "herramientas": []}
    assert a_modelo(Contribucion, Contribucion(**datos)).agente == "analista"
    assert a_modelo(Contribucion, datos).agente == "analista"
    assert a_modelo(Contribucion, {"lc": 1, "type": "constructor", "kwargs": datos}).agente == "analista"


def test_accion_critica_pausa_y_se_reanuda_con_aprobacion():
    async def flujo():
        redis = RedisFalso()
        grafo = ensamblar_grafo(nodos_completos(redis), InMemorySaver())
        await grafo.ainvoke(estado_inicial("tarea de prueba"), CONFIG)
        pausado = await grafo.aget_state(CONFIG)
        assert pausado.next == ("aprobacion",)
        assert pausado.interrupts[0].value["accion"] == "revertir_despliegue"

        await grafo.ainvoke(Command(resume={"aprobado": True, "comentario": "ok"}), CONFIG)
        final = await grafo.aget_state(CONFIG)
        return redis, final

    redis, final = asyncio.run(flujo())
    assert final.next == ()
    assert "APROBADA" in final.values["resultado_accion"]
    assert json.loads(redis.listas[CLAVE_AUDITORIA][0])["accion"] == "revertir_despliegue"
    assert [c.agente for c in contribuciones(final.values)] == ["investigador", "analista"]


def test_rechazo_no_ejecuta_la_accion():
    async def flujo():
        redis = RedisFalso()
        grafo = ensamblar_grafo(nodos_completos(redis), InMemorySaver())
        await grafo.ainvoke(estado_inicial("tarea"), CONFIG)
        await grafo.ainvoke(Command(resume={"aprobado": False, "comentario": "no"}), CONFIG)
        return redis, await grafo.aget_state(CONFIG)

    redis, final = asyncio.run(flujo())
    assert "RECHAZADA" in final.values["resultado_accion"]
    assert CLAVE_AUDITORIA not in redis.listas


def test_sin_accion_critica_no_pasa_por_aprobacion():
    async def flujo():
        grafo = ensamblar_grafo(nodos_completos(RedisFalso(), accion="ninguna"), InMemorySaver())
        await grafo.ainvoke(estado_inicial("tarea"), CONFIG)
        return await grafo.aget_state(CONFIG)

    final = asyncio.run(flujo())
    assert final.next == ()
    assert final.values["resultado_accion"] == ""


def test_el_estado_sobrevive_a_un_grafo_nuevo_con_el_mismo_checkpointer():
    """Simula un reinicio: otro grafo (otro proceso) con el mismo checkpointer retoma la pausa."""

    async def flujo():
        checkpointer = InMemorySaver()
        redis = RedisFalso()
        await ensamblar_grafo(nodos_completos(redis), checkpointer).ainvoke(estado_inicial("tarea"), CONFIG)
        grafo_nuevo = ensamblar_grafo(nodos_completos(redis), checkpointer)
        assert (await grafo_nuevo.aget_state(CONFIG)).next == ("aprobacion",)
        await grafo_nuevo.ainvoke(Command(resume={"aprobado": True}), CONFIG)
        return await grafo_nuevo.aget_state(CONFIG)

    assert "APROBADA" in asyncio.run(flujo()).values["resultado_accion"]
