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

## Backend integration (all 5 student modules wired in)

Per the Release 1 brief, the frontend never talks to the MCP/RAG servers
directly — only each module's own backend does, acting as an MCP client
(via the official `mcp` SDK's Streamable HTTP client, wrapped in each
backend's own copy of `mcp_client.py` — copied rather than shared as a
package, the same reason each backend already keeps its own
agent.py/ai_service.py) and RAG client (a plain `requests` call, since the
RAG server is a normal REST API, not MCP). Every one of the 5 backends now
exposes:

- `POST /api/mcp/query` — calls one of the shared MCP server's tools
  scoped to the authenticated user (whitelisted per module: expense ->
  `get_expenses`/`get_categories`, budget -> `get_budgets`, income ->
  `get_income_sources`/`get_pay_schedules`, savings -> `get_savings_goals`,
  bills -> `get_bills`/`get_bills_summary`).
- `POST /api/rag/ask` — forwards `{"message": "..."}` to the shared RAG
  server's `/answer_question` and returns the grounded answer, citations,
  and confidence category as-is.

bill-tracker had no prior AI integration at all (no agent.py/ai_service.py
existed) — these two routes are its first. The other four modules keep
their existing Release 0 agentic loops (agent.py / ai_service.py)
untouched; the new routes are additive, not a replacement.

Verified from this environment (no Docker, so the underlying databases and
Ollama/AI-Mode were not running): both routes correctly reach the live MCP
server and RAG server and get back well-formed, structured error responses
identifying exactly which downstream service was unreachable — proving the
MCP/RAG client wiring itself is correct end to end. Full success-path
verification (real data, real generated answers) needs `docker compose up`
on a machine with Docker, plus `ai-mode`, `mcp-server`, and `rag-server`
each started locally via their `run_local.sh` scripts first.
