"""Agente investigador: consulta la documentación de Kestrel con recuperación híbrida (BM25 + Pinecone)."""

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from app.agents.common import crear_nodo_especialista
from app.graph.state import EstadoOrquestador
from app.rag.hibrido import RecuperadorHibrido
from app.rag.modelos import Categoria, Fragmento

PROMPT_INVESTIGADOR = """Eres el investigador de un equipo de análisis de la plataforma ficticia Kestrel.
Tu única fuente es la documentación interna, que consultas con la herramienta buscar_documentacion.

- Haz una búsqueda por cada tema que necesites; puedes llamar a la herramienta varias veces.
- Responde con los datos EXACTOS encontrados (cifras, umbrales, plazos y reglas) y cita la fuente de cada dato entre corchetes, por ejemplo [despliegues-00].
- No hagas cálculos ni conclusiones: eso le corresponde al analista.
- Si algo no aparece en la documentación, dilo explícitamente en lugar de suponerlo."""


class BuscarDocumentacionArgs(BaseModel):
    """Entrada validada de la herramienta de búsqueda."""

    consulta: str = Field(min_length=3, max_length=300, description="Pregunta o tema a buscar, en lenguaje natural.")
    categoria: Categoria | None = Field(
        default=None,
        description='Acota la búsqueda: "arquitectura", "api", "operaciones" (incidentes, monitoreo, respaldos), '
        '"procesos" (despliegues, onboarding) o "seguridad". Omítela si no estás seguro.',
    )


class ResultadoBusqueda(BaseModel):
    """Salida validada de la herramienta, que se entrega al modelo como texto citado."""

    consulta: str
    categoria: Categoria | None
    fragmentos: list[Fragmento]

    def como_texto(self) -> str:
        if not self.fragmentos:
            return "Sin resultados para esa consulta."
        return "\n\n---\n\n".join(
            f"[{f.chunk_id} | {f.fuente} | encontrado por: {', '.join(f.metodos)}]\n{f.texto}" for f in self.fragmentos
        )


def crear_herramienta_busqueda(recuperador: RecuperadorHibrido) -> BaseTool:
    @tool("buscar_documentacion", args_schema=BuscarDocumentacionArgs)
    async def buscar_documentacion(consulta: str, categoria: Categoria | None = None) -> str:
        """Busca en la documentación interna de Kestrel los fragmentos más relevantes para una consulta.

        Combina búsqueda semántica y por palabras clave. Devuelve cada fragmento con su
        identificador y archivo de origen, para citarlo."""
        fragmentos = await recuperador.buscar(consulta, categoria)
        return ResultadoBusqueda(consulta=consulta, categoria=categoria, fragmentos=fragmentos).como_texto()

    return buscar_documentacion


def entrada_investigador(estado: EstadoOrquestador) -> str:
    # Solo la instrucción del supervisor: el investigador no necesita el resto del contexto.
    return estado["instruccion"]


def crear_investigador(llm: BaseChatModel, recuperador: RecuperadorHibrido, recursion_limit: int):
    agente = create_react_agent(llm, [crear_herramienta_busqueda(recuperador)], prompt=PROMPT_INVESTIGADOR)
    return crear_nodo_especialista("investigador", agente, entrada_investigador, recursion_limit)
