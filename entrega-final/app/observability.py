"""Observabilidad con Arize Phoenix (OpenTelemetry + OpenInference).

Se instrumenta solo LangChain/LangGraph y los spans de los jobs. No se usa auto_instrument ni un
proveedor global, porque FastAPI registraría cada consulta HTTP de estado y llenaría Phoenix de
ruido (problema detectado en la Pre-entrega 7).
"""

from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from phoenix.otel import register

from app.settings import Settings


def iniciar_observabilidad(settings: Settings) -> TracerProvider:
    proveedor = register(
        project_name=settings.phoenix_project,
        endpoint=settings.phoenix_endpoint,
        auto_instrument=False,
        set_global_tracer_provider=False,
        batch=True,
    )
    LangChainInstrumentor().instrument(tracer_provider=proveedor)
    return proveedor


def detener_observabilidad(proveedor: TracerProvider) -> None:
    """Envía las trazas pendientes antes de apagar la API."""
    LangChainInstrumentor().uninstrument()
    proveedor.shutdown()
