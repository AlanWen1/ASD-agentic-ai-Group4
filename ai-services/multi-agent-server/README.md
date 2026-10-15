# Shared Multi-Agent Server — Release 2

A shared local Planner → Worker → Reviewer workflow used by the five feature
modules. This server is a host process, not a Docker service. The Finance
Application remains the shared login/home page and receives no Release 2 UI.

## Agents and flow

1. Planner (qwen2.5:0.5b) converts the request into a structured plan and
   identifies evidence, assumptions, checks, risks and success criteria.
2. Worker (qwen2.5:0.5b) performs the requested analysis using that plan and
   the supplied application evidence. It proposes results; it cannot write to
   finance databases or execute transactions.
3. Reviewer (llama3.1:8b) checks the Worker output against the plan/evidence
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
- The qwen2.5:0.5b and llama3.1:8b models available in Ollama

From the repository root:

    ollama pull qwen2.5:0.5b
    ollama pull llama3.1:8b
    ./ai-services/multi-agent-server/run_local.sh

The service listens on port 5102. It binds to 0.0.0.0 by default so
Dockerised backends can reach the host through host.docker.internal. The API
requires the X-Multi-Agent-Key header. Its development default is
local-dev-key-change-me: set MULTI_AGENT_API_KEY to a private value in both
the host-server environment and application environment beyond a local demo.
Do not add this process to docker-compose.yml.

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
