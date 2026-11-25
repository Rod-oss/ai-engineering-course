"""Esquemas Pydantic de la salida del sistema RAG."""
from pydantic import BaseModel, Field, model_validator

RESPUESTA_DESCONOCIDA = "No lo sé."


class RespuestaRAG(BaseModel):
    """Lo que debe devolver el modelo: la respuesta y las fuentes que usó."""

    respuesta: str = Field(
        min_length=1,
        description="Respuesta en español basada solo en el CONTEXTO, o exactamente 'No lo sé.'",
    )
    encontrada: bool = Field(
        description="true si el CONTEXTO contiene la respuesta; false en caso contrario."
    )
    fuentes: list[str] = Field(
        default_factory=list,
        description="Referencias de los fragmentos usados, con el formato archivo.md#número.",
    )

    @model_validator(mode="after")
    def verificar_coherencia(self) -> "RespuestaRAG":
        if self.encontrada and not self.fuentes:
            raise ValueError("Si la respuesta se encontró, debe citar al menos una fuente")
        if not self.encontrada:
            self.respuesta = RESPUESTA_DESCONOCIDA
            self.fuentes = []
        return self


class ResultadoRAG(BaseModel):
    """Resultado final de get_rag_response(), con las fuentes ya verificadas."""

    pregunta: str
    respuesta: str
    encontrada: bool
    fuentes: list[str]
    fragmentos_recuperados: list[str]