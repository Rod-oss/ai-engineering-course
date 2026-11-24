#!/usr/bin/env bash
# Se ejecuta cada vez que el Codespace se enciende.

MODELO="qwen2.5:1.5b"

# 1. Encender el servidor de Ollama en segundo plano, si no está encendido
if ! curl -s http://127.0.0.1:11434 > /dev/null; then
  echo ">>> Encendiendo el servidor de Ollama"
  setsid nohup ollama serve > /tmp/ollama.log 2>&1 &
fi

# 2. Esperar hasta 30 segundos a que el servidor responda
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:11434 > /dev/null; then
    break
  fi
  sleep 1
done

# 3. Descargar el modelo solo si todavía no está
if ! ollama list | grep -q "$MODELO"; then
  echo ">>> Descargando el modelo $MODELO"
  ollama pull "$MODELO"
fi

echo ">>> Ollama listo en http://127.0.0.1:11434"