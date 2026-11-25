#!/usr/bin/env bash
# Levanta todo el sistema (API + Redis + Phoenix) con un solo comando.
#
#   ./run.sh          construye y levanta los servicios, y espera a que la API responda
#   ./run.sh logs     muestra los logs de la API
#   ./run.sh stop     detiene los servicios (los datos de Redis y Phoenix se conservan)
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-up}" in
  logs) exec docker compose logs -f api ;;
  stop) exec docker compose down ;;
  up) ;;
  *) echo "Uso: ./run.sh [up|logs|stop]"; exit 1 ;;
esac

command -v docker >/dev/null || { echo "Docker no está instalado."; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Se creó .env a partir de .env.example."
fi

# Las claves pueden venir del entorno (secrets de Codespaces) o de una línea en .env.
for variable in GEMINI_API_KEY PINECONE_API_KEY; do
  if [ -z "${!variable:-}" ] && ! grep -qE "^${variable}=.+" .env; then
    echo "Falta ${variable}: créala como secret de Codespaces o agrégala a .env."
    exit 1
  fi
done

docker compose up --build -d

echo "Esperando a que la API esté lista..."
for _ in $(seq 1 90); do
  if curl -fs http://localhost:8000/health >/dev/null 2>&1; then
    echo
    echo "Sistema listo:"
    echo "  API y documentación:  http://localhost:8000/docs"
    echo "  Trazas (Phoenix):     http://localhost:6006"
    exit 0
  fi
  sleep 2
done

echo "La API no respondió a tiempo. Revisa los logs con: ./run.sh logs"
exit 1
