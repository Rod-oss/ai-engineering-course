"""Agente analista: cálculos exactos y comparación con umbrales. No accede a la documentación."""
import ast
import json
import operator
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.agents.common import crear_nodo_especialista
from app.state import EstadoOrquestador

PROMPT_ANALISTA = """Eres el analista cuantitativo de un equipo de análisis de la plataforma ficticia Kestrel.
Recibes una instrucción del supervisor y, cuando existen, los datos que encontró el investigador.

- Haz TODOS los cálculos con tus herramientas; nunca calcules mentalmente.
- Usa exactamente los umbrales y cifras que recibes; no inventes valores.
- Compara cada valor medido con su umbral usando comparar_con_umbral.
- Responde con cada resultado numérico, la herramienta que lo produjo y una conclusión breve.
- Si te falta un dato para un cálculo, dilo explícitamente."""

_OPERADORES = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
               ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg}


def _evaluar(nodo: ast.AST) -> float:
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)):
        return float(nodo.value)
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES:
        return _OPERADORES[type(nodo.op)](_evaluar(nodo.left), _evaluar(nodo.right))
    if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERADORES:
        return _OPERADORES[type(nodo.op)](_evaluar(nodo.operand))
    raise ValueError("Solo se permiten números y los operadores + - * / ** y paréntesis")


@tool
def calcular(expresion: str) -> str:
    """Evalúa de forma segura una expresión aritmética, por ejemplo "(43200 - 38) / 43200 * 100".
    Admite números decimales, + - * / ** y paréntesis. Úsala para cualquier cálculo."""
    return json.dumps({"expresion": expresion, "resultado": round(_evaluar(ast.parse(expresion, mode="eval").body), 6)})


@tool
def analizar_disponibilidad(minutos_caida: float, slo_porcentaje: float, dias_periodo: int = 30) -> str:
    """Calcula la disponibilidad real de un periodo y el estado del presupuesto de error.

    Recibe los minutos totales sin servicio, el objetivo de disponibilidad (SLO) en porcentaje,
    por ejemplo 99.9, y la duración del periodo en días. Devuelve la disponibilidad lograda,
    el presupuesto de error en minutos, el porcentaje consumido, los minutos restantes y si
    se cumple el SLO."""
    minutos_totales = dias_periodo * 24 * 60
    presupuesto = minutos_totales * (1 - slo_porcentaje / 100)
    disponibilidad = (minutos_totales - minutos_caida) / minutos_totales * 100
    return json.dumps({
        "minutos_del_periodo": minutos_totales,
        "disponibilidad_porcentaje": round(disponibilidad, 4),
        "presupuesto_error_minutos": round(presupuesto, 2),
        "presupuesto_consumido_porcentaje": round(minutos_caida / presupuesto * 100, 2),
        "minutos_restantes": round(presupuesto - minutos_caida, 2),
        "cumple_slo": disponibilidad >= slo_porcentaje,
    })


@tool
def comparar_con_umbral(metrica: str, valor: float, umbral: float,
                        condicion_de_alerta: Literal["mayor_que", "mayor_o_igual", "menor_que", "menor_o_igual"]) -> str:
    """Compara un valor medido con un umbral documentado e indica si se activa la condición.

    `condicion_de_alerta` describe cuándo el valor incumple el umbral. Por ejemplo, para la
    regla "revertir si la tasa de errores supera el 2 %", usa valor=2.4, umbral=2 y
    condicion_de_alerta="mayor_que"."""
    activa = {"mayor_que": valor > umbral, "mayor_o_igual": valor >= umbral,
              "menor_que": valor < umbral, "menor_o_igual": valor <= umbral}[condicion_de_alerta]
    return json.dumps({"metrica": metrica, "valor": valor, "umbral": umbral,
                       "condicion_de_alerta": condicion_de_alerta, "se_activa": activa})


def entrada_analista(estado: EstadoOrquestador) -> str:
    # La instrucción más SOLO los datos del investigador, que son los que el analista necesita.
    datos = [c.resultado for c in estado["contribuciones"] if c.agente == "investigador"]
    if not datos:
        return estado["instruccion"]
    return estado["instruccion"] + "\n\nDATOS DEL INVESTIGADOR:\n" + "\n\n".join(datos)


def crear_analista(llm: BaseChatModel):
    agente = create_react_agent(llm, [calcular, analizar_disponibilidad, comparar_con_umbral],
                                prompt=PROMPT_ANALISTA)
    return crear_nodo_especialista("analista", agente, entrada_analista)