"""Modelos Pydantic de la capa RAG."""

from typing import Literal

from pydantic import BaseModel, Field

Categoria = Literal["arquitectura", "api", "operaciones", "procesos", "seguridad"]
Metodo = Literal["vectorial", "lexico"]


class Fragmento(BaseModel):
    """Un fragmento de la documentación devuelto por un buscador."""

    chunk_id: str = Field(min_length=1)
    fuente: str
    categoria: str
    texto: str
    metodos: list[Metodo] = Field(default_factory=list, description="Buscadores que encontraron el fragmento.")
    puntaje: float = Field(default=0.0, description="Puntaje del buscador o puntaje RRF tras la fusión.")
