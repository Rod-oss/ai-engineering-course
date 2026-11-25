"""Punto de entrada de la API: arma todas las capas al arrancar y las cierra al apagar.

uvicorn app.main:app --port 8000
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from redis.asyncio import Redis

from app.api.routes import router
from app.graph.builder import construir_grafo
from app.llm import crear_embeddings, crear_llm
from app.observability import detener_observabilidad, iniciar_observabilidad
from app.rag.documentos import cargar_fragmentos
from app.rag.hibrido import RecuperadorHibrido
from app.rag.lexico import BuscadorLexico
from app.rag.vectorial import BuscadorVectorial, ConexionPinecone
from app.services.jobs import RepositorioJobs
from app.services.worker import Worker
from app.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()  # falla aquí, con un mensaje claro, si falta alguna variable de entorno
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()
    proveedor = iniciar_observabilidad(settings)
    pinecone = await ConexionPinecone.abrir(settings)

    # BM25 se construye en un hilo: fragmentar y tokenizar es CPU y no debe bloquear el event loop.
    fragmentos = await asyncio.to_thread(cargar_fragmentos, settings.data_dir)
    recuperador = RecuperadorHibrido(
        BuscadorVectorial(pinecone.indice, crear_embeddings(settings), settings.pinecone_namespace),
        BuscadorLexico(fragmentos),
        top_k=settings.rag_top_k,
        peso_vectorial=settings.rag_peso_vectorial,
        rrf_k=settings.rag_rrf_k,
    )
    logger.info(
        "RAG híbrido listo: %d fragmentos en BM25, índice Pinecone '%s'", len(fragmentos), settings.pinecone_index
    )

    try:
        async with AsyncRedisSaver.from_conn_string(settings.redis_url) as checkpointer:
            await checkpointer.asetup()
            grafo = construir_grafo(settings, crear_llm(settings), recuperador, redis, checkpointer)
            jobs = RepositorioJobs(redis, settings.job_ttl_dias * 24 * 3600)
            worker = Worker(
                grafo,
                jobs,
                proveedor.get_tracer("kestrel.api"),
                settings.worker_concurrency,
                settings.recursion_limit_grafo,
                max_reintentos=settings.job_max_reintentos,
                espera_reintento_s=settings.job_espera_reintento_s,
            )
            worker.iniciar()
            recuperados = await worker.recuperar_pendientes()
            logger.info("Jobs recuperados tras el arranque: %d", recuperados)
            app.state.redis, app.state.jobs, app.state.worker, app.state.grafo = redis, jobs, worker, grafo
            yield
            await worker.detener()
    finally:
        await pinecone.cerrar()
        await asyncio.to_thread(detener_observabilidad, proveedor)
        await redis.aclose()


app = FastAPI(
    title="Kestrel Intelligence System",
    version="1.0.0",
    description="RAG híbrido + agentes con supervisor + aprobación humana, sobre LangGraph con checkpoints en Redis "
    "y trazas en Arize Phoenix.",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/", include_in_schema=False)
async def raiz() -> RedirectResponse:
    return RedirectResponse("/docs")
