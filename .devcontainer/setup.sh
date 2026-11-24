#!/usr/bin/env bash
# Se ejecuta una sola vez, cuando el Codespace se crea o se reconstruye.
set -e

echo ">>> Instalando zstd (necesario para descomprimir Ollama)"
sudo apt-get update
sudo apt-get install -y zstd

echo ">>> Instalando Ollama"
curl -fsSL https://ollama.com/install.sh | sh