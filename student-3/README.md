# Student 3 - Income & Pay Schedule Manager

**Owner:** Yongjian Zhou
**Project:** AI-Assisted Personal Money Management System
**Release:** Release 1 (continues Release 0)

## Overview

The Income & Pay Schedule Manager allows authenticated users to manage income
sources, expected payment schedules, and received payments. It calculates
monthly income summaries with Python and SQL, then uses a local Ollama model to
explain the calculated results and answer questions through an AI chat box.

The feature is implemented as three independently containerised microservices:

```text
Frontend (3003)
    -> HTTP
Backend/API (5003)
    -> HTTP
Database API (6003)
    ->
SQLite database
```

The Backend/API never opens the SQLite database directly.

## Main Features

- Complete CRUD operations for income sources
- Complete CRUD operations for pay schedules
- Automatic generation of expected pay dates
- Monthly expected, received, outstanding, and variance calculations
- Filtering by dashboard month
- Shared authentication with bearer-token validation
- Per-user data isolation
- Ollama/Qwen monthly income analysis
- Free-form AI chat grounded in the authenticated user's income data
- Automated Python tests and GitHub Actions CI

## Services and Ports

| Service | Port | Responsibility |
|---|---:|---|
| Student 3 Frontend | 3003 | Web interface and Backend/API proxy |
| Student 3 Backend/API | 5003 | Authentication, business logic, calculations, and AI |
| Student 3 Database API | 6003 | SQLite ownership and CRUD operations |

The integrated application also uses the shared services on ports 3000, 5000,
and 6000.

## Database Tables

### `income_sources`

Stores the source name, income type, standard amount, payment frequency,
active status, and owning user.

### `pay_schedules`

Stores expected and received payment dates, expected and actual amounts,
payment status, notes, linked income source, and owning user.

Both tables include at least ten seeded records for demonstration and testing.

## Authentication and Data Isolation

Users sign in through the shared Finance Application on
`http://localhost:3000`. The shared UI sends the authentication token to the
Student 3 frontend. The frontend stores the token locally, removes it from the
visible URL, and sends it as an `Authorization: Bearer ...` header.

The Backend/API validates the token with the shared access service and passes
only the authenticated user's ID to the Database API. Database queries include
that user ID so one user cannot access another user's income records.

## AI Design

The approved local model is `qwen2.5:0.5b`, served through Ollama.

Python and SQL calculate:

- expected and received totals;
- outstanding income;
- payment counts;
- source totals; and
- actual-versus-expected variance.

The model only explains trusted calculated context. It is instructed not to
invent financial data or provide investment, tax, legal, or financial-product
advice.

## Run the Integrated Application

From the repository root:

```powershell
docker compose up --build -d
```

Open the shared application:

```text
http://localhost:3000
```

After signing in, select **Income & Pay Schedule Manager**.

## Run Student 3 with the Existing Shared Login Service

The standalone Compose file starts only the three Student 3 services. Keep the
shared login application and authentication Database API running on ports
3000 and 6000. Host AI services are started separately, as below. Do not run
both Compose projects at once: they publish the same Student 3 ports.

```powershell
docker compose -f .\docker-compose.student-3.yml up --build -d
```

Open:

```text
http://localhost:3003
```


## Release 1 Integration

Release 0 income CRUD, date generation, monthly calculations and AI chat remain.
Release 1 connects the feature UI through its own backend to two shared host
services:

| UI action | Student 3 backend | Shared host service |
|---|---|---|
| Income sources via MCP | `POST /api/mcp/query`, tool `get_income_sources` | MCP, `5100/mcp` |
| Pay schedules via MCP | `POST /api/mcp/query`, tool `get_pay_schedules` | MCP, `5100/mcp` |
| Knowledge question | `POST /api/rag/ask` | RAG, `5101/answer_question` |
| Existing income analysis/chat | `/api/ai/analyse`, `/api/ai/chat` | AI-Mode, `5099`, then Ollama |

MCP requests use the authenticated user ID. Request-supplied owner IDs are not
forwarded. RAG returns `answer`, `citations` and `confidence_category`; a question
outside the corpus returns `insufficient` with empty citations. Dependency and
invalid-response errors return 502; RAG timeouts return 504. Model text, source
names and citations are rendered as text or escaped HTML.

AI-Mode, MCP, RAG and the agentic review loop are host processes, not Compose
services. Install dependencies in the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r student-3/backend/requirements.txt
```

Start each host service in its own PowerShell window from the repository root:

```powershell
# Window 1
$env:PORT = "5099"
$env:OLLAMA_URL = "http://localhost:11434"
.\.venv\Scripts\python.exe .\ai-services\ai-mode\service.py
```

```powershell
# Window 2
$env:PORT = "5100"
.\.venv\Scripts\python.exe .\ai-services\mcp-server\server.py
```

```powershell
# Window 3
$env:PORT = "5101"
$env:AI_MODE_URL = "http://localhost:5099"
.\.venv\Scripts\python.exe .\ai-services\rag-server\rag_server.py
```

Normal local runs enable all three modes. The Student 3 backend reads
`AI_ENABLED`, `MCP_ENABLED` and `RAG_ENABLED` (default `true`). Its `/health`
response exposes the configured modes. CI sets all three to `false` and checks
that the corresponding authenticated endpoints return 503 with a `*_DISABLED`
code without contacting shared AI services.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q student-3/tests ai-services/agentic-loop/tests
node --test student-3/tests/test_frontend_rendering.cjs
```

The workflow builds and starts real containers for shared authentication and the
three Student 3 layers, then runs `student-3/scripts/ci_smoke.py`. This checks CRUD,
ownership, monthly monetary totals and disabled-mode responses through the
frontend proxy using disposable accounts. Run the smoke script only against an
isolated test stack with all three modes disabled. The workflow's volume cleanup
runs on the disposable GitHub runner.

See [Release 1 evidence checklist](RELEASE1-EVIDENCE.md) for remaining submission
records. A local passing test is not evidence of a successful GitHub Actions run.
