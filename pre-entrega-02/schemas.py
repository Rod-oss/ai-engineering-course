"""Contrato de salida del pipeline, definido con Pydantic."""
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class NivelCriticidad(str, Enum):
    """Valores permitidos para la criticidad."""

    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


class ExtraccionTecnica(BaseModel):
    """Información técnica extraída de un texto sin procesar."""

    tecnologias: list[str] = Field(
        min_length=1,
        description=(
            "Tecnologías mencionadas explícitamente en el texto: lenguajes, "
            "frameworks, bases de datos, servicios o herramientas."
        ),
    )
    nivel_de_criticidad: NivelCriticidad = Field(
        description="Gravedad de la situación descrita: baja, media o alta."
    )
    resumen_tecnico: str = Field(
        min_length=10,
        max_length=300,
        description="Resumen técnico de una sola oración, en español.",
    )

    @field_validator("tecnologias")
    @classmethod
    def limpiar_tecnologias(cls, valores: list[str]) -> list[str]:
        """Quita espacios, vacíos y duplicados, conservando el orden."""
        limpias: list[str] = []
        for valor in valores:
            valor = valor.strip()
            if valor and valor.lower() not in {v.lower() for v in limpias}:
                limpias.append(valor)
        if not limpias:
            raise ValueError("La lista de tecnologías no puede estar vacía")
        return limpias