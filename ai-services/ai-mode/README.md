# AI-Mode

Release 0 requirement: a shared AI-mode capability (Ollama runtime + one or
more approved open-source LLMs — Qwen, Llama, or DeepSeek) that every
microservice's backend uses.

**Current state (Release 1 update):** this is a real shared service, not
just a library — but as of the Release 1 MCP/RAG integration work it is no
longer defined in the main `docker-compose.yml`. The Release 1 brief
requires AI-Mode, the MCP server, the RAG server, and the agentic loop to
all run **locally and non-containerised**, so `service.py` now runs as a
plain host process instead of a Docker service:

```bash
./ai-services/ai-mode/run_local.sh
```

Start this **before** `docker compose up` — every backend's containerised
service reaches it via `host.docker.internal`, Docker's special hostname
for "the machine the containers are running on", not the old
Docker-network service name:

| Backend | Env var (in docker-compose.yml) | Now (Release 1) |
| --- | --- | --- |
| expense-category-tracker | `OLLAMA_URL` | `http://host.docker.internal:5099` |
| bill-tracker | `OLLAMA_URL` | `http://host.docker.internal:5099` |
| student-1-budget | `OLLAMA_URL` | `http://host.docker.internal:5099` |
| student-5 | `OLLAMA_API_URL` | `http://host.docker.internal:5099/api/generate` |
| student-3 | `OLLAMA_BASE_URL` | `http://host.docker.internal:5099/v1` |

(Release 0 had this as an `ai-mode-service` container in `docker-compose.yml`,
reached via the Docker-network name `ai-mode-service:5099`. That still
works exactly this way in `docker-compose.student-3.yml`, which is
Student 3's own self-contained CI compose file with its own containerised
Ollama — that file is untouched by this change and is a separate, known
inconsistency to note in Known Issues, since Release 1 asks for AI-Mode/
MCP/RAG to be disabled rather than containerised during CI.)

Each backend also gets an `extra_hosts: ["host.docker.internal:host-gateway"]`
entry in `docker-compose.yml` now, so `host.docker.internal` resolves the
same way on Linux Docker hosts as it does by default on Docker Desktop
(macOS/Windows).

`service.py` exposes the exact same paths Ollama itself exposes for both
API styles already in use across the team (native `/api/generate`,
`/api/chat`, `/api/tags` for the first four backends; OpenAI-compatible
`/v1/chat/completions`, `/v1/models` for student-3) and proxies each one
straight through to the real Ollama runtime, byte-for-byte. That's why
**no backend's Python code changed** — only the URL each one was already
configured with, via its own `OLLAMA_URL` / `OLLAMA_API_URL` /
`OLLAMA_BASE_URL` environment variable. Every backend's own tests, its
Dockerfile, and its `docker build ./<module>/backend` CI step are
unaffected.

`ollama_client.py` is the shared implementation the service is built on
(`generate`, `chat`, `health_check` — see its docstring) — `service.py`
uses it for the `/health` route and its underlying `requests` session for
the raw proxy routes. `ollama_client.py` is also available directly to any
new code that wants to call it as a library instead of over HTTP.

Why proxy instead of making every backend import a shared Python module
directly: the five backends are five separately-built Docker images with
build contexts scoped to their own folder (`./bill-tracker/backend`, etc.),
matching each student's own CI workflow (`docker build -t X ./module/backend`).
Getting a shared *module* into each of those images would mean changing
every Dockerfile's build context to the repo root and rewriting every COPY
path — a much bigger, riskier change to five people's Docker/CI setups for
the same result. A shared *service* gets the same "one implementation,
one place to change timeouts/error-handling/model policy" benefit without
touching anyone's Dockerfile or CI.

Run this folder's own tests with:

```bash
cd ai-services/ai-mode && python3 -m pytest tests/ -q
```
