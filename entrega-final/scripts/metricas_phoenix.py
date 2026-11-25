"""Métricas de la prueba de carga calculadas a partir de las trazas guardadas en Phoenix.

Uso:
    python scripts/metricas_phoenix.py              # trazas de los últimos 30 minutos
    python scripts/metricas_phoenix.py --minutos 120

Por cada job suma sus trazas (job.iniciar y, si hubo HITL o un reinicio, job.reanudar o job.continuar):
latencia de procesamiento, llamadas al LLM, tokens y costo estimado.
Después resume p50, p95 y costo por ejecución.
"""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from phoenix.client import Client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
PHOENIX_URL = os.getenv("PHOENIX_URL", "http://localhost:6006")
PROYECTO = os.getenv("PHOENIX_PROJECT", "kestrel-intelligence")
# Precios del nivel de pago de gemini-3.5-flash-lite, en USD por millón de tokens.
PRECIO_ENTRADA_1M = float(os.getenv("PRECIO_ENTRADA_1M", "0.30"))
PRECIO_SALIDA_1M = float(os.getenv("PRECIO_SALIDA_1M", "2.50"))
SPANS_DE_JOB = {"job.iniciar", "job.reanudar", "job.continuar"}
TOKENS_ENTRADA = "attributes.llm.token_count.prompt"
TOKENS_SALIDA = "attributes.llm.token_count.completion"
RESULTADOS = Path(__file__).resolve().parent.parent / "resultados"
ARCHIVO = RESULTADOS / "metricas_phoenix.json"
ARCHIVO_CARGA = RESULTADOS / "carga.json"


def percentil(valores: list[float], p: float) -> float:
    """Percentil con interpolación lineal (el mismo método que numpy usa por defecto)."""
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    posicion = (len(ordenados) - 1) * p / 100
    inferior = int(posicion)
    superior = min(inferior + 1, len(ordenados) - 1)
    return ordenados[inferior] + (ordenados[superior] - ordenados[inferior]) * (posicion - inferior)


def obtener_job_id(raices):
    """Lee el atributo job.id del span; Phoenix puede entregarlo como columna plana o anidado."""
    if "attributes.job.id" in raices:
        ids = raices["attributes.job.id"]
    elif "attributes.job" in raices:
        ids = raices["attributes.job"].apply(lambda v: v.get("id") if isinstance(v, dict) else None)
    else:
        print("Aviso: las trazas no traen job.id; se agrupa por traza.")
        ids = raices["context.trace_id"]
    return ids.fillna(raices["context.trace_id"])


def main(minutos: int) -> None:
    desde = datetime.now(UTC) - timedelta(minutes=minutos)
    df = Client(base_url=PHOENIX_URL).spans.get_spans_dataframe(
        project_identifier=PROYECTO, start_time=desde, limit=100_000
    )

    raices = df[df["name"].isin(SPANS_DE_JOB)].copy()
    if raices.empty:
        print(f"No hay trazas de jobs en los últimos {minutos} minutos.")
        return
    raices["latencia_s"] = (raices["end_time"] - raices["start_time"]).dt.total_seconds()
    raices["job_id"] = obtener_job_id(raices)
    # Si existe resultados_carga.json, se miden solo los jobs de esa prueba de carga.
    if ARCHIVO_CARGA.exists():
        ids_carga = {j["job_id"] for j in json.loads(ARCHIVO_CARGA.read_text(encoding="utf-8"))["jobs"]}
        raices = raices[raices["job_id"].isin(ids_carga)]
        print(f"Midiendo solo los {len(ids_carga)} jobs de {ARCHIVO_CARGA.name}")
        if raices.empty:
            print("Esos jobs no están en la ventana de tiempo; aumenta --minutos.")
            return

    # Tokens y número de llamadas al LLM de cada traza.
    llm = df[df["span_kind"] == "LLM"]
    tokens = llm.groupby("context.trace_id")[[TOKENS_ENTRADA, TOKENS_SALIDA]].sum()
    llamadas = llm.groupby("context.trace_id").size().rename("llamadas_llm")
    raices = raices.drop(columns=[TOKENS_ENTRADA, TOKENS_SALIDA], errors="ignore")
    raices = raices.join(tokens, on="context.trace_id").join(llamadas, on="context.trace_id")
    raices[[TOKENS_ENTRADA, TOKENS_SALIDA, "llamadas_llm"]] = raices[
        [TOKENS_ENTRADA, TOKENS_SALIDA, "llamadas_llm"]
    ].fillna(0)
    raices["costo_usd"] = (
        raices[TOKENS_ENTRADA] / 1e6 * PRECIO_ENTRADA_1M + raices[TOKENS_SALIDA] / 1e6 * PRECIO_SALIDA_1M
    )

    # Un job con HITL tiene dos trazas: se suman para obtener el costo por ejecución.
    por_job = (
        raices.groupby("job_id")
        .agg(
            trazas=("name", "count"),
            latencia_s=("latencia_s", "sum"),
            llamadas_llm=("llamadas_llm", "sum"),
            tokens_entrada=(TOKENS_ENTRADA, "sum"),
            tokens_salida=(TOKENS_SALIDA, "sum"),
            costo_usd=("costo_usd", "sum"),
        )
        .reset_index()
        .sort_values("latencia_s")
    )
    for columna in ("llamadas_llm", "tokens_entrada", "tokens_salida"):
        por_job[columna] = por_job[columna].astype(int)
    por_job["latencia_s"] = por_job["latencia_s"].round(2)
    por_job["costo_usd"] = por_job["costo_usd"].round(6)
    por_job["job_id"] = por_job["job_id"].str[:8]

    latencias = por_job["latencia_s"].tolist()
    costos = por_job["costo_usd"].tolist()
    resumen = {
        "fecha_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "ventana_minutos": minutos,
        "jobs": len(por_job),
        "trazas": len(raices),
        "llamadas_llm": int(por_job["llamadas_llm"].sum()),
        "latencia_procesamiento_s": {
            "p50": round(percentil(latencias, 50), 2),
            "p95": round(percentil(latencias, 95), 2),
            "max": max(latencias),
        },
        "costo_por_ejecucion_usd": {
            "promedio": round(sum(costos) / len(costos), 6),
            "p95": round(percentil(costos, 95), 6),
            "max": max(costos),
        },
        "costo_total_usd": round(sum(costos), 6),
        "precios_usd_por_millon": {"entrada": PRECIO_ENTRADA_1M, "salida": PRECIO_SALIDA_1M},
        "nota": "Costo estimado con precios del nivel de pago. La prueba usó el nivel gratuito, "
        "así que el costo real fue 0. La latencia mide desde que el worker toma el job "
        "(no incluye la espera en cola).",
    }
    RESULTADOS.mkdir(exist_ok=True)
    ARCHIVO.write_text(
        json.dumps({"resumen": resumen, "jobs": por_job.to_dict(orient="records")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Proyecto Phoenix: {PROYECTO} | últimos {minutos} minutos\n")
    print(por_job.to_string(index=False))
    print("\n=== Métricas desde Phoenix ===")
    lat, cos = resumen["latencia_procesamiento_s"], resumen["costo_por_ejecucion_usd"]
    print(f"Jobs: {resumen['jobs']} | Trazas: {resumen['trazas']} | Llamadas al LLM: {resumen['llamadas_llm']}")
    print(f"Latencia de procesamiento: p50 {lat['p50']} s | p95 {lat['p95']} s | máx. {lat['max']} s")
    print(f"Costo por ejecución (USD): promedio {cos['promedio']:.6f} | p95 {cos['p95']:.6f} | máx. {cos['max']:.6f}")
    print(f"Costo total de la prueba (USD): {resumen['costo_total_usd']:.6f}")
    print(f"Guardado en resultados/{ARCHIVO.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Métricas de latencia y costo desde Phoenix")
    parser.add_argument("--minutos", type=int, default=30)
    main(parser.parse_args().minutos)
