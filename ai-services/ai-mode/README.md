# AI-Mode

Release 0 requirement: a shared AI-mode capability (Ollama runtime + one or
more approved open-source LLMs — Qwen, Llama, or DeepSeek) that every
microservice's backend uses.

**Current state:** this is now a real shared service, not just a library.
`service.py` is a small Flask app (`ai-mode-service` in `docker-compose.yml`
and `docker-compose.student-3.yml`, port 5099) that is the *only* thing in
the whole application that talks to the shared Ollama runtime directly.
Every backend is pointed at it instead of at Ollama:

| Backend | Env var (in docker-compose.yml) | Before | Now |
| --- | --- | --- | --- |
| expense-category-tracker | `OLLAMA_URL` | `http://host.docker.internal:11434` | `http://ai-mode-service:5099` |
| bill-tracker | `OLLAMA_URL` | `http://host.docker.internal:11434` | `http://ai-mode-service:5099` |
| student-1-budget | `OLLAMA_URL` | `http://host.docker.internal:11434` | `http://ai-mode-service:5099` |
| student-5 | `OLLAMA_API_URL` | `http://host.docker.internal:11434/api/generate` | `http://ai-mode-service:5099/api/generate` |
| student-3 | `OLLAMA_BASE_URL` | `http://host.docker.internal:11434/v1` | `http://ai-mode-service:5099/v1` |

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
