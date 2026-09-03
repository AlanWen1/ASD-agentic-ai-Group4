# AI Services

The project spec's reference repository structure calls for a shared
`ai-services/` directory holding the AI capabilities used across the whole
team application: `ai-mode/`, `mcp-server/`, `rag-server/`, and
`multi-agent-server/`.

**Current state:** `ai-mode/` is now a real, running shared service
(`ai-mode-service` in `docker-compose.yml`, port 5099) that every backend
is pointed at instead of talking to the shared Ollama runtime directly —
see `ai-mode/README.md` for exactly how each of the five backends was
repointed and why no backend code had to change to adopt it.
`mcp-server/`, `rag-server/`, and `multi-agent-server/` are still
placeholders that give each sub-folder a home once the team gets to those
releases.

- `ai-mode/` — Release 0 requirement: AI-mode + Ollama runtime + approved
  LLM(s). Implemented as a shared proxy service every backend now calls —
  see `ai-mode/README.md`.
- `mcp-server/` — Release 1 requirement. Not implemented yet.
- `rag-server/` — Release 1 requirement. Not implemented yet.
- `multi-agent-server/` — Release 2 requirement (Planner/Worker/Reviewer
  agents). Not implemented yet.
