"""Herramientas de los agentes: entradas y salidas validadas con Pydantic."""

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.agents.analyst_agent import (
    ResultadoComparacion,
    ResultadoDisponibilidad,
    analizar_disponibilidad,
    calcular,
    comparar_con_umbral,
)
from app.agents.research_agent import crear_herramienta_busqueda
from app.agents.supervisor import DecisionSupervisor, corregir_decision
from app.graph.state import Contribucion
from app.rag.modelos import Fragmento


def test_calcular_es_seguro():
    assert json.loads(calcular.invoke({"expresion": "(43200 - 38) / 43200 * 100"}))["resultado"] == pytest.approx(
        99.912037
    )
    with pytest.raises(ValueError):
        calcular.invoke({"expresion": "__import__('os').system('ls')"})


def test_disponibilidad_devuelve_un_modelo_valido():
    salida = analizar_disponibilidad.invoke({"minutos_caida": 12, "slo_porcentaje": 99.9})
    resultado = ResultadoDisponibilidad.model_validate_json(salida)
    assert resultado.presupuesto_error_minutos == pytest.approx(43.2)
    assert resultado.minutos_restantes == pytest.approx(31.2)
    assert resultado.cumple_slo


def test_disponibilidad_rechaza_argumentos_invalidos():
    with pytest.raises(ValidationError):
        analizar_disponibilidad.invoke({"minutos_caida": -5, "slo_porcentaje": 99.9})
    with pytest.raises(ValidationError):
        analizar_disponibilidad.invoke({"minutos_caida": 5, "slo_porcentaje": 150})


def test_comparar_con_umbral():
    salida = comparar_con_umbral.invoke(
        {"metrica": "tasa de errores", "valor": 2.4, "umbral": 2, "condicion_de_alerta": "mayor_que"}
    )
    assert ResultadoComparacion.model_validate_json(salida).se_activa
    with pytest.raises(ValidationError):
        comparar_con_umbral.invoke({"metrica": "x", "valor": 1, "umbral": 2, "condicion_de_alerta": "aprox"})


class RecuperadorFalso:
    async def buscar(self, consulta: str, categoria: str | None = None) -> list[Fragmento]:
        return [
            Fragmento(
                chunk_id="despliegues-00",
                fuente="despliegues.md",
                categoria="procesos",
                texto="Revertir si supera el 2 %",
                metodos=["lexico", "vectorial"],
            )
        ]


def test_busqueda_valida_la_categoria_y_cita_la_fuente():
    herramienta = crear_herramienta_busqueda(RecuperadorFalso())
    texto = asyncio.run(herramienta.ainvoke({"consulta": "umbral de reversión", "categoria": "procesos"}))
    assert "[despliegues-00 | despliegues.md" in texto
    with pytest.raises(ValidationError):
        asyncio.run(herramienta.ainvoke({"consulta": "umbral", "categoria": "finanzas"}))
    with pytest.raises(ValidationError):
        asyncio.run(herramienta.ainvoke({"consulta": "x"}))  # menos de 3 caracteres


def test_supervisor_no_finaliza_sin_ambos_especialistas():
    solo_investigador = [Contribucion(paso=1, agente="investigador", instruccion="i", resultado="r")]
    decision = DecisionSupervisor(evaluacion="listo", siguiente="sintesis", instruccion="redacta")
    corregida = corregir_decision(decision, solo_investigador, "tarea")
    assert corregida.siguiente == "analista"
