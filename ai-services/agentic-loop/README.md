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
7. All reviews + MCP/RAG validation

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
eight tools, and call each discovered expected tool with
`VALIDATION_USER_ID` (default 1).

A downstream database error is reported separately from an MCP protocol error.

## RAG validation

The RAG mode checks `http://localhost:5101`, refreshes the corpus, runs
three representative retrieval queries, and tests grounded
`/answer_question` generation. It prints retrieved source IDs, distances,
citations, confidence, and dependency errors.

## Environment variables

- `AGENT_MODEL` (default `llama3.1:8b`)
- `OLLAMA_URL` (default `http://localhost:11434`)
- `MCP_SERVER_URL` (default `http://localhost:5100/mcp`)
- `RAG_SERVER_URL` (default `http://localhost:5101`)
- `VALIDATION_USER_ID` (default `1`)
- `AGENT_MAX_ITERATIONS` (default `3`)