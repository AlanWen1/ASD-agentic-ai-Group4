#!/usr/bin/env bash
# Starts the shared MCP server as a local (non-containerised) host
# process, per the Release 1 requirement that AI-Mode, the MCP server,
# the RAG server, and the agentic loop all run locally rather than as
# docker-compose services.
#
# Usage:
#   ./ai-services/mcp-server/run_local.sh
#
# Start this BEFORE `docker compose up`, alongside ai-mode's own
# run_local.sh — backends will reach this at
# http://host.docker.internal:5100 once wired in.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

export PORT="${PORT:-5100}"

echo "Starting MCP server on http://localhost:${PORT}/mcp"
python3 server.py
