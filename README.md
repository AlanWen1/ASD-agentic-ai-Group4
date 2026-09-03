# ASD 2026 Group 4 — Agentic AI Personal Finance Application

A microservices-based personal finance application built for the ASD 2026
group project. Five independently developed frontend/backend/database
microservice sets are integrated behind one shared login and one unified
home page, and each module uses an open-source LLM (via [Ollama](https://ollama.com/))
for AI-assisted functionality.

## Modules

| Module | Owner's feature | Frontend | Backend | Database |
| --- | --- | --- | --- | --- |
| `finance-application` | Shared login/registration + unified home page | :3000 | :5000 | :6000 |
| `student-1-budget` | Budget Manager | :3001 | :5001 | (init-only container, see `student-1-budget/database`) |
| `expense-category-tracker` | Expense & Category Manager | :3002 | :5002 | :6002 |
| `student-3` | Income & Pay Schedule Manager | :3003 | :5003 | :6003 |
| `bill-tracker` | Bill Tracker | :3004 | :5004 | :6004 |
| `student-5` | Savings Goal Manager | :3005 | :5005 | :6005 |

`finance-application` is the shared entry point: it handles registration,
login, and issues each user a session token, and its home page
(`http://localhost:3000/`) links out to all five feature modules. Signing in
there and clicking through to a module carries the session token along, so
users don't have to log in again per module (see each module's `FINANCE_URL`
handling in its frontend `app.py`).

There is also a sixth, shared (non-feature) service: `ai-mode-service`
(`ai-services/ai-mode/`, port `:5099`). It's the only thing every backend
above talks to for AI calls — see `ai-services/ai-mode/README.md`.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker + Docker Compose)
- [Ollama](https://ollama.com/) running locally on the host, with the model
  each service expects pulled — currently `qwen2.5:0.5b` for most services
  (check each service's `OLLAMA_MODEL` environment variable in
  `docker-compose.yml` if that changes):

  ```bash
  ollama pull qwen2.5:0.5b
  ```

- Python 3.11+ and `pip` if you want to run any module's tests locally
  outside Docker.

## Running the whole application

From the repository root:

```bash
docker compose up --build
```

This builds and starts every service defined in `docker-compose.yml`. Once
it's up, open `http://localhost:3000/`, register or sign in, and use the
home page to reach each module.

To stop everything:

```bash
docker compose down
```

If you've changed a Dockerfile and Docker seems to be using a stale image,
rebuild with `docker compose build --no-cache <service>` for that one
service, or `docker compose up --build` to rebuild everything.

## Running a single module

Each student's CI workflow (`.github/workflows/student-N.yml`) shows the
exact compile/test/build steps used for that module. Some modules also have
their own standalone Docker Compose file for running just their own stack
(`docker-compose.student-1.yml`, `docker-compose.student-3.yml`).

## Running tests

```bash
./scripts/test/test-all.sh
```

Runs every module's compile-check and pytest suite from the repo root. Note
that a couple of modules' tests expect their backend to already be running
(see the script's comments) — check that module's own workflow file for the
exact startup sequence if a test fails with a connection error here.

## Repository layout

- `finance-application/`, `bill-tracker/`, `student-1-budget/`,
  `expense-category-tracker/`, `student-3/`, `student-5/` — each
  microservice set's `frontend/`, `backend/`, and `database/` code, tests,
  and Dockerfile.
- `shared/` — the shared CSS theme (`theme.css`) used across every module's
  frontend so the app looks like one product.
- `docker-compose.yml` — runs the full integrated application.
- `.github/workflows/` — one CI workflow per student module.
- `docs/` — architecture notes, planning documents, and per-release
  submission evidence (see the README in each subfolder for what belongs
  there and what's still missing).
- `ai-services/` — shared AI-mode/MCP/RAG/Multi-Agent services described in
  the project spec; `ai-mode/` is implemented as a running shared service
  every backend's AI calls go through, the rest are still placeholders —
  see `ai-services/README.md` for the current state.
- `scripts/` — build and test helper scripts.

## AI-assisted development

This project was built with AI assistance (see the project spec's AI Usage
Policy). All AI-generated code, documentation, and tests were reviewed and
validated by the responsible student before being committed.
