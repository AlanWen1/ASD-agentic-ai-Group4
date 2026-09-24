# RAG Server

Release 1 requirement (see project spec section 4.2): one shared,
**non-containerised** local Retrieval-Augmented Generation server, used
by all five student features to produce grounded answers with citations
and a confidence category.

**Current state:** implemented. `rag_pipeline.py` holds the three
capabilities the brief asks for (`refresh_corpus`, `retrieve_context`,
`answer_question`); `rag_server.py` is a thin Flask REST wrapper around
them, the same style as `../ai-mode/service.py`, so any of the five
backends can call it with a plain `requests` call.

## How retrieval works

The knowledge base is `corpus/corpus.jsonl` — 24 short documents about
this app's own features (what each module does), budgeting concepts, and
FAQs (how to add an expense, what an overdue bill means, etc.) — see the
file for the full list. `rag_pipeline.py` builds a small hand-rolled
TF-IDF + cosine-similarity index over it at startup (or on
`refresh_corpus`). This is a deliberate choice over a vector database and
embedding model (e.g. chromadb + sentence-transformers): the knowledge
base is small and static, so a heavier dependency would add setup risk
without adding real retrieval quality. See `rag_pipeline.py`'s module
docstring for the tradeoff and how to swap in a real vector store later
without changing the three public functions' signatures.

Grounded generation goes through the shared **AI-Mode** service (see
`../ai-mode/`), not Ollama directly — same as every module's own backend
already does — so `answer_question` only ever forwards a prompt built
from retrieved chunks; it never calls an LLM with unretrieved, made-up
context.

## Run it

```bash
./run_local.sh
```

or directly:

```bash
pip install -r requirements.txt
python3 rag_server.py
```

Starts a local host process listening on `http://localhost:5101`. It
expects AI-Mode to already be running on `http://localhost:5099` (see
`../ai-mode/run_local.sh`) for `answer_question` to produce real
generated answers — `retrieve_context` and `refresh_corpus` work without
it. **Do not** add this to `docker-compose.yml` as a service — Release 1
requires AI-Mode, the MCP server, the RAG server, and the agentic loop to
all be non-containerised.

## Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | GET | Reports whether the corpus is loaded and how many chunks |
| `/refresh_corpus` | POST | Reload `corpus/corpus.jsonl` and rebuild the index |
| `/retrieve_context?query=...&k=5` | GET/POST | Top-k relevant chunks, each with `chunk_id`, `source_id`, `distance`, `text` |
| `/answer_question?query=...&k=5` | GET/POST | Grounded answer with `citations`, `confidence_category`, `retrieval_summary` |

`confidence_category` is one of `high` / `medium` / `low` / `insufficient`.
When nothing relevant enough is retrieved (`insufficient`), the server
returns a fixed "I don't have enough information" answer with empty
citations **without calling the LLM at all** — see `MIN_CONTEXT_SCORE` in
`rag_pipeline.py`.

## Testing

```bash
python3 -m pytest tests/ -q      # 10 tests, all mocked for the LLM call — no live services needed
python3 rag_pipeline.py          # runs refresh_corpus, retrieve_context, and answer_question once each
```

Verified end-to-end (in this environment, without a real Ollama running):
`/health`, `/retrieve_context` (returns correctly ranked real chunks —
e.g. querying "how do bills become overdue" correctly surfaces the
overdue-bills chunk first), and `/answer_question` (correctly propagates
a clean, structured error through the whole chain — RAG server → AI-Mode
→ Ollama — instead of crashing, when Ollama isn't reachable). Once Ollama
is running locally, `/answer_question` will return a real generated
answer instead of that error.

## Wiring into a feature (in progress)

Each backend is expected to call this server through its own backend/API,
not directly from the frontend — see the project spec's "RAG and Grounded
Response Flow" requirement. That client-side wiring is being added
per-module, starting with Expense & Category Manager as the reference
implementation (same as MCP — see `../mcp-server/README.md`).
