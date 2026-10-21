# Local Agentic Review Loop

Uses Ollama **llama3.1:8b** locally and follows:

```
Plan -> Act -> Observe -> Review -> Adapt
```

It is deliberately **non-containerised** and is not added to Docker Compose.

## Modes

1. Database review
2. Implementation review
3. Microservices architecture review
4. DevOps pipeline review
5. MCP validation
6. RAG validation
7. Multi-Agent Workflow Review
8. Testing Report Review
9. Cloud Deployment Report Review
10. All reviews + validations

The terminal asks the user to select a mode unless `--mode` is supplied.

## Run

Install the requested local model:

```bash
ollama pull llama3.1:8b
```

Then:

```bash
./ai-services/agentic-loop/run_local.sh
```

Direct examples:

```bash
python3 ai-services/agentic-loop/agent_review.py --mode mcp
python3 ai-services/agentic-loop/agent_review.py --mode rag
python3 ai-services/agentic-loop/agent_review.py --mode all
```

## MCP validation

The MCP mode uses the official Python MCP SDK to connect to
`http://localhost:5100/mcp`, initialise a session, discover the expected
nine tools (including `get_budget_overview`), and call each discovered expected tool with
`VALIDATION_USER_ID` (default 1).

A downstream database error is reported separately from an MCP protocol error.

## RAG validation

The RAG mode checks `http://localhost:5101`, refreshes the corpus, runs
five feature retrieval queries, and tests grounded
`/answer_question` generation. It checks citation IDs against retrieved sources and also tests an unrelated
question for `insufficient` confidence with empty citations. It prints answers,
citations, confidence, retrieval counts and dependency errors.

Both validation modes return a nonzero exit status on failure. A connected MCP
server alone does not pass: discovery and all nine downstream tool calls must
succeed. Keep all five feature Database APIs running before collecting evidence.

## Environment variables

- `AGENT_MODEL` (default `llama3.1:8b`)
- `OLLAMA_URL` (default `http://localhost:11434`)
- `MCP_SERVER_URL` (default `http://localhost:5100/mcp`)
- `RAG_SERVER_URL` (default `http://localhost:5101`)
- `VALIDATION_USER_ID` (default `1`)
- `AGENT_MAX_ITERATIONS` (default `3`)


## Release 2 evidence and logs

Use `--mode multi_agent --workflow-evidence FILE.json` with a workflow downloaded
from Income Manager or saved by the terminal client. The exported run must contain
Planner/Worker/Reviewer coordination events and a real final human decision.
Without an export, live validation creates a run but does not approve it; missing
human-review evidence is reported as incomplete. Reviewer analysis uses the plan,
supplied evidence, proposal, audit and human history.

Use `--mode testing` after retaining security and individual endpoint results, and
`--mode deployment` after retaining local/cloud deployment results in docs/reports.
All modes save timestamped text and JSON under docs/release-2/evidence/reviews
(or `--output-dir`). MCP, RAG and Multi-Agent validation failures return nonzero.
Model unavailability is labelled `deterministic_fallback`; such logs must not be
presented as a successful LLM-assisted review or a completed human release decision.
