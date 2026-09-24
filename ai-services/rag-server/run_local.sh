#!/usr/bin/env bash
# Starts the shared RAG server as a local (non-containerised) host
# process, per the Release 1 requirement that AI-Mode, the MCP server,
# the RAG server, and the agentic loop all run locally rather than as
# docker-compose services.
#
# Usage:
#   ./ai-services/rag-server/run_local.sh
#
# Start this BEFORE `docker compose up`, alongside ai-mode's and
# mcp-server's own run_local.sh scripts. This also expects ai-mode
# itself to be running (it calls AI_MODE_URL for grounded generation).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

export PORT="${PORT:-5101}"
export AI_MODE_URL="${AI_MODE_URL:-http://localhost:5099}"

echo "Starting RAG server on http://localhost:${PORT} (AI-Mode: ${AI_MODE_URL})"
python3 rag_server.py
