"""Observabilidad con Phoenix (OpenTelemetry + OpenInference).

Solo instrumentamos LangChain/LangGraph y nuestros spans de jobs.
No usamos auto_instrument para no registrar cada consulta HTTP de estado
(GET /tasks/{job_id}), que llenaría Phoenix de ruido y distorsionaría la latencia.
"""
from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register

from app.config import PHOENIX_ENDPOINT, PHOENIX_PROJECT


def iniciar_observabilidad():
    proveedor = register(
        project_name=PHOENIX_PROJECT,
        endpoint=PHOENIX_ENDPOINT,
        auto_instrument=False,
        set_global_tracer_provider=False,
        batch=True,
    )
    LangChainInstrumentor().instrument(tracer_provider=proveedor)
    return proveedor.get_tracer("kestrel.api")
