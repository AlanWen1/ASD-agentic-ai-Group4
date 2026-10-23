# Shared Multi-Agent Server — Release 2

A shared local Planner → Worker → Reviewer workflow used by the five feature
modules. This server is a host process, not a Docker service. The Finance
Application remains the shared login/home page and receives no Release 2 UI.

## Agents and flow

1. Planner (qwen2.5:7b) converts the request into a structured plan and
   identifies evidence, assumptions, checks, risks and success criteria.
2. Worker (qwen2.5:7b) performs the requested analysis using that plan and
   the supplied application evidence. It proposes results; it cannot write to
   finance databases or execute transactions.
3. Reviewer (qwen2.5:7b by default) checks the Worker output against the plan/evidence
   and records findings, risks, evidence gaps and recommendations.
4. Human review is mandatory. A person must approve, request a correction or
   reject the result. Corrections re-run Worker and Reviewer using the feedback
   (maximum three correction cycles). Decisions and prior drafts are persisted.

Frontend UI → module Backend/API → local Multi-Agent Server → Planner → Worker
→ Reviewer → Human Review → response to Frontend UI.

The server stores run status and review history in local SQLite (runs.sqlite3
beside this file by default). Set MULTI_AGENT_DB_PATH to change the path.

## Requirements and startup

- Python 3.11+
- Ollama running locally at http://localhost:11434 by default
- The qwen2.5:0.5b model available in Ollama (used by all three agents by default)

From the repository root:

    ollama pull qwen2.5:0.5b
    ./ai-services/multi-agent-server/run_local.sh

The service listens on port 5102. Planner, Worker and Reviewer default to qwen2.5:0.5b to reduce local memory pressure. On a machine with enough RAM/VRAM, set REVIEWER_MODEL=llama3.1:8b before launching to opt into the larger Reviewer model. It binds to 0.0.0.0 by default so
Dockerised backends can reach the host through host.docker.internal. Ollama
chat is read as a stream rather than waiting for one complete response; this
lets long generations make progress without hitting a single 180-second idle
read. The read-timeout allowance defaults to 600 seconds and the module
backend/frontend proxies allow up to 2100 seconds for the three agents to
run sequentially. The API
requires the X-Multi-Agent-Key header. Its development default is
local-dev-key-change-me: set MULTI_AGENT_API_KEY to a private value in both
the host-server environment and application environment beyond a local demo.
Do not add this process to docker-compose.yml.

### Ollama performance and timeout settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `MULTI_AGENT_OLLAMA_TIMEOUT_SECONDS` | `600` | Maximum idle wait for an Ollama response chunk; streamed tokens can keep a request alive longer overall |
| `MULTI_AGENT_OLLAMA_CONNECT_TIMEOUT_SECONDS` | `10` | Time allowed to establish a connection to Ollama |
| `MULTI_AGENT_OLLAMA_KEEP_ALIVE` | `10m` | Ask Ollama to keep each model loaded temporarily between calls |
| `MULTI_AGENT_OLLAMA_NUM_PREDICT` | `768` | Maximum generated tokens per agent response |
| `MULTI_AGENT_OLLAMA_NUM_CTX` | `8192` | Context size requested for the agent call |

After changing server code or these environment variables, stop the running
Multi-Agent Server with Ctrl+C and start `run_local.sh` again.

If a task still times out, first check that Ollama is responsive and both
models are present with `ollama list`; try a simple direct chat using
`qwen2.5:0.5b` before retrying the multi-agent task. The Planner, Worker and
Reviewer run sequentially, so their combined duration is naturally longer
than a single AI-mode chat request. Keep evidence focused on the task rather
than sending full exports if they are not needed.

## Terminal use

Start the server in one terminal. In another terminal:

    python3 ai-services/multi-agent-server/cli.py --module bills \
      --task "Summarise pending and overdue bills and suggest a priority order" \
      --evidence-file ./my-bills-evidence.json

Or provide JSON inline:

    python3 ai-services/multi-agent-server/cli.py --module savings \
      --task "Assess progress towards my goals" \
      --evidence-json '{"goals":[{"goal_name":"Emergency fund","target_amount":5000,"current_amount":1200}]}'

The CLI prints the plan, Worker proposal and Reviewer assessment and then
requires a human to choose approve, correct or reject. Omitting evidence is
allowed for experimentation, but the agents should identify evidence gaps;
do not treat unsupported output as personalised financial advice.

## HTTP API

All API calls except /health require X-Multi-Agent-Key.

- GET /health: service and configured models.
- POST /runs: starts all three agents and returns awaiting_human_review.
- GET /runs?module=bills&user_id=123: recent runs for the matching owner.
- GET /runs/<id>?module=bills&user_id=123: read a run with matching owner.
- POST /runs/<id>/decision: approve, correct (requires feedback), or reject.

Example request body:

    {"module":"bills","user_id":"123","task":"Prioritise upcoming bills","evidence":{"bills":[]}}

The initial POST runs Planner, Worker and Reviewer but never auto-approves.
Decision requests must repeat the run's module and user_id; mismatches receive
404. Run states include planning, working, awaiting_human_review, correcting,
approved, rejected and failed.

## Module use cases

- Budget Manager: review allocations and identify overspend risks or gaps.
- Expense & Category Manager: analyse spending patterns and category consistency.
- Income & Pay Schedule Manager: compare expected/received income and flag timing gaps.
- Bill Tracker: identify pending/overdue bills and prioritisation considerations.
- Savings Goal Manager: assess goal progress and possible contribution trade-offs.

Integrations are advisory. They do not automatically create, update or delete
budgets, expenses, income, payments, bills or savings goals.

## Tests

    python3 -m pytest ai-services/multi-agent-server/tests -q

Tests mock Ollama and do not require live models or databases.
