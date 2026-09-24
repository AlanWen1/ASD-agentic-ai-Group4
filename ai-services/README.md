# AI Services

The project spec's reference repository structure calls for a shared
`ai-services/` directory holding the AI capabilities used across the whole
team application: `ai-mode/`, `mcp-server/`, `rag-server/`, and
`multi-agent-server/`.

**Current state (Release 1):** `ai-mode/` is a real, running shared
service that every backend is pointed at instead of talking to the shared
Ollama runtime directly. As of the Release 1 MCP/RAG work it runs as a
**local, non-containerised host process** (`./ai-services/ai-mode/run_local.sh`)
rather than a `docker-compose.yml` service — the Release 1 brief requires
AI-Mode, the MCP server, the RAG server, and the agentic loop to all be
non-containerised, so this was moved out of `docker-compose.yml` and every
backend now reaches it at `host.docker.internal:5099` instead of the old
Docker-network name `ai-mode-service:5099`. See `ai-mode/README.md` for
the before/after table.

`mcp-server/` and `rag-server/` are now both implemented the same way —
local host processes, no Docker service — so all three shared AI
capabilities (`ai-mode/`, `mcp-server/`, `rag-server/`) follow one
consistent non-containerised pattern and connection convention.

- `ai-mode/` — Release 0 requirement: AI-mode + Ollama runtime + approved
  LLM(s). Implemented as a shared proxy service every backend now calls —
  see `ai-mode/README.md`. Non-containerised as of Release 1.
- `mcp-server/` — Release 1 requirement. Implemented — see
  `mcp-server/README.md` for the 8 tools and how to run it.
- `rag-server/` — Release 1 requirement. Implemented — see
  `rag-server/README.md` for the knowledge base, retrieval approach, and
  how to run it.
- `multi-agent-server/` — Release 2 requirement (Planner/Worker/Reviewer
  agents). Not implemented yet.
