#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt
export AGENT_MODEL="${AGENT_MODEL:-llama3.1:8b}"
export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
export MCP_SERVER_URL="${MCP_SERVER_URL:-http://localhost:5100/mcp}"
export RAG_SERVER_URL="${RAG_SERVER_URL:-http://localhost:5101}"
export AGENT_MAX_ITERATIONS="${AGENT_MAX_ITERATIONS:-3}"
python3 agent_review.py