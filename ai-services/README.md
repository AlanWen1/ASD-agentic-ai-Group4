# AI Services

The project spec's reference repository structure calls for a shared
`ai-services/` directory holding the AI capabilities used across the whole
team application: `ai-mode/`, `mcp-server/`, `rag-server/`, and
`multi-agent-server/`.

**Current state (honest note, not aspirational):** this directory did not
exist before — each student's backend currently calls Ollama directly from
its own code (see e.g. `expense-category-tracker/backend/app.py`,
`bill-tracker/backend/app.py`, `student-3/backend/app.py`,
`student-1-budget/backend/agent.py`). That works functionally (every module
can reach the shared Ollama runtime at `host.docker.internal:11434` and use
an approved LLM), but it means there is no single shared AI service the way
the reference architecture diagrams it. This folder is a placeholder that
documents the gap and gives each sub-folder a home once the team decides
whether to centralise this logic.

- `ai-mode/` — Release 0 requirement: AI-mode + Ollama runtime + approved
  LLM(s). Not centralised yet; see the per-backend Ollama calls above.
- `mcp-server/` — Release 1 requirement. Not implemented yet.
- `rag-server/` — Release 1 requirement. Not implemented yet.
- `multi-agent-server/` — Release 2 requirement (Planner/Worker/Reviewer
  agents). Not implemented yet.
