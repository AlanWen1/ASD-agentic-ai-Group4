#!/usr/bin/env bash
# Starts the shared AI-Mode service as a local (non-containerised) host
# process, per the Release 1 requirement that AI-Mode, the MCP server, the
# RAG server, and the agentic loop all run locally rather than as
# docker-compose services.
#
# Usage:
#   ./ai-services/ai-mode/run_local.sh
#
# Start this BEFORE `docker compose up` — the five backends are configured
# to reach it at http://host.docker.internal:5099 (see docker-compose.yml).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:0.5b}"
export PORT="${PORT:-5099}"

echo "Starting AI-Mode service on http://localhost:${PORT} (upstream Ollama: ${OLLAMA_URL})"
python3 service.py
