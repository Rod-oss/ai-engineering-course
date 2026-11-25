"""Pipeline LCEL de extracción de entidades técnicas con salida validada."""
import logging
import os

import openai
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from schemas import ExtraccionTecnica

logger = logging.getLogger("pipeline")

# Forma de pedir JSON estructurado al modelo: "json_schema" o "function_calling".
METODO_SALIDA_ESTRUCTURADA = "json_schema"
MAX_INTENTOS = 3


class LLMSettings(BaseModel):
    """Configuración del modelo, validada con Pydantic como en la Pre-entrega 1."""

    api_key: SecretStr = Field(min_length=1)
    base_url: str | None = None
    model: str = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0)
    timeout: float = Field(default=30.0, gt=0)

    @classmethod
    def desde_entorno(cls, **cambios) -> "LLMSettings":
        valores = {
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "base_url": os.getenv("OPENAI_BASE_URL") or None,
            "model": os.getenv("OPENAI_MODEL", ""),
            "timeout": os.getenv("OPENAI_TIMEOUT", "30"),
        }
        valores.update(cambios)
        return cls(**valores)


class SalidaInvalidaError(Exception):
    """El modelo devolvió un JSON incompleto, mal formado o fuera del esquema."""


class PipelineError(Exception):
    """No se logró una extracción válida tras todos los intentos."""


# Errores ante los que tiene sentido reintentar.
ERRORES_REINTENTABLES = (
    SalidaInvalidaError,               # JSON inválido o fuera del esquema
    openai.LengthFinishReasonError,    # respuesta cortada (finish_reason=length)
    openai.RateLimitError,             # límite de tasa (429)
    openai.APIConnectionError,         # red caída o tiempo agotado
    openai.InternalServerError,        # error 5xx del proveedor
)

INSTRUCCIONES_FORMATO = """Devuelve exclusivamente los campos del esquema:
- tecnologias: tecnologías mencionadas explícitamente en el texto (lenguajes, frameworks, bases de datos, servicios o herramientas). No inventes tecnologías que no aparezcan.
- nivel_de_criticidad: "alta" si hay caída del servicio, pérdida de datos, fallos en producción o riesgos de seguridad; "media" si hay degradación del rendimiento o errores intermitentes; "baja" si es informativo o una mejora planificada.
- resumen_tecnico: una sola oración en español, de máximo 200 caracteres."""

PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Eres un analista técnico de software que extrae información estructurada.\n\n"
            "{instrucciones_formato}",
        ),
        ("human", "Texto a analizar:\n\n{texto}"),
    ]
).partial(instrucciones_formato=INSTRUCCIONES_FORMATO)


def _describir(exc: BaseException | None, limite: int = 200) -> str:
    """Mensaje breve y legible para los logs."""
    if exc is None:
        return "error desconocido"
    if isinstance(exc, openai.LengthFinishReasonError):
        return "respuesta cortada por límite de tokens (finish_reason=length)"
    texto = " ".join(str(exc).split())
    return texto if len(texto) <= limite else texto[:limite] + "..."


def _registrar_intento(entrada: dict) -> dict:
    """Primer paso de la cadena: se ejecuta en cada intento y lo registra."""
    estado = entrada["_estado"]
    estado["intentos"] += 1
    if estado["intentos"] == 1:
        logger.info("[%s] Intento 1 de %d: enviando texto al modelo",
                    estado["etiqueta"], MAX_INTENTOS)
    else:
        logger.warning("[%s] Reintento: intento %d de %d (el anterior no produjo un objeto válido)",
                       estado["etiqueta"], estado["intentos"], MAX_INTENTOS)
    return entrada


def _registrar_intento(entrada: dict) -> dict:
    """Primer paso de la cadena: se ejecuta en cada intento y lo registra."""
    estado = entrada["_estado"]
    estado["intentos"] += 1
    logger.info("[%s] Intento %d de %d: enviando texto al modelo",
                estado["etiqueta"], estado["intentos"], MAX_INTENTOS)
    return entrada


def _validar_salida(resultado: dict) -> ExtraccionTecnica:
    """Revisa finish_reason y el resultado del parser antes de aceptar el objeto."""
    finish_reason = resultado["raw"].response_metadata.get("finish_reason")
    if finish_reason == "length":
        logger.warning("Respuesta cortada por límite de tokens (finish_reason=length)")
        raise SalidaInvalidaError("El modelo se quedó sin tokens y el JSON quedó incompleto")
    if resultado["parsing_error"] is not None:
        logger.warning("JSON mal formado o fuera del esquema: %s", _describir(resultado["parsing_error"]))
        raise SalidaInvalidaError(f"JSON inválido: {_describir(resultado['parsing_error'])}")
    if resultado["parsed"] is None:
        logger.warning("El modelo no devolvió ningún objeto (finish_reason=%s)", finish_reason)
        raise SalidaInvalidaError("El modelo no devolvió ningún objeto")
    logger.info("Validación con Pydantic correcta (finish_reason=%s)", finish_reason)
    return resultado["parsed"]


def construir_cadena(**cambios) -> Runnable:
    """Arma la cadena LCEL. `cambios` permite ajustar la configuración, p. ej. max_tokens."""
    settings = LLMSettings.desde_entorno(**cambios)
    modelo = ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.timeout,
        max_retries=0,  # los reintentos los gestiona .with_retry()
    )
    modelo_estructurado = modelo.with_structured_output(
        ExtraccionTecnica, method=METODO_SALIDA_ESTRUCTURADA, include_raw=True
    )

    cadena = (
        RunnableLambda(_registrar_intento)
        | PROMPT
        | modelo_estructurado
        | RunnableLambda(_validar_salida)
    )
    return cadena.with_retry(
        retry_if_exception_type=ERRORES_REINTENTABLES,
        wait_exponential_jitter=True,
        stop_after_attempt=MAX_INTENTOS,
    )


async def process_text(text: str, cadena: Runnable | None = None,
                       etiqueta: str = "texto") -> ExtraccionTecnica:
    """Ejecuta el pipeline de forma asíncrona y devuelve un objeto validado."""
    estado = {"intentos": 0, "etiqueta": etiqueta}
    cadena = cadena or construir_cadena()
    logger.info("[%s] Procesando texto de %d caracteres", etiqueta, len(text))
    try:
        resultado = await cadena.ainvoke(
            {"texto": text, "_estado": estado},
            config={"callbacks": [RegistroReintentos(etiqueta)]},
        )
    except Exception as exc:
        logger.error("[%s] Extracción fallida tras %d intento(s): %s",
                     etiqueta, estado["intentos"], _describir(exc))
        raise PipelineError(
            f"Sin extracción válida tras {estado['intentos']} intento(s): {_describir(exc)}"
        ) from exc
    logger.info("[%s] Extracción validada en %d intento(s)", etiqueta, estado["intentos"])
    return resultado