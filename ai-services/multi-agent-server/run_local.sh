#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
export MULTI_AGENT_API_KEY="${MULTI_AGENT_API_KEY:-local-dev-key-change-me}"
export MULTI_AGENT_PORT="${MULTI_AGENT_PORT:-5102}"
export PLANNER_MODEL="${PLANNER_MODEL:-qwen2.5:0.5b}"
export WORKER_MODEL="${WORKER_MODEL:-qwen2.5:0.5b}"
export REVIEWER_MODEL="${REVIEWER_MODEL:-llama3.1:8b}"
export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
exec python3 service.py