# Student 3 Plan -> Act -> Observe -> Adapt record

Use this file as a truthful evidence template. Replace bracketed placeholders with screenshots, commit hashes, timestamps, and actual observations from the team repository.

## PLAN

**Goal:** Implement Yongjian Zhou's independent Income & Pay Schedule Manager with frontend, backend/API, Database API, SQLite, CRUD, deterministic calculations, Docker, testing, and Ollama/Qwen chat.

**Acceptance checks:**

- Ports are `3003`, `5003`, and `6003`.
- Both SQLite tables contain at least ten seeded records.
- Both resources support Create, Read, Update, and Delete from the UI.
- The backend accesses SQLite only through HTTP to the Database API.
- AI is callable from the frontend and answers questions about the selected month's data.
- Python/SQL, rather than the LLM, calculates dates and money.
- Student 3 tests and container builds pass.

**Prompt used:** `[Paste the development/review prompt used with the approved AI tool.]`

## ACT

Implemented:

- `student-3/frontend/`
- `student-3/backend/`
- `student-3/database/`
- `student-3/tests/`
- `.github/workflows/student-3.yml`
- Student 3 entries in the shared `docker-compose.yml`

**Commit/PR evidence:** `[Add commit hashes and pull-request URL.]`

## OBSERVE

Record actual results:

```text
pytest result: [paste result]
Docker build result: [paste result]
Docker Compose result: [paste result]
Frontend URL tested: http://localhost:3003
CRUD result: [describe]
AI question and response: [paste concise example]
```

Issues found during observation:

1. `[Issue and evidence]`
2. `[Issue and evidence]`

## ADAPT

Changes made after observing results:

1. `[Fix or improvement, affected file, and reason]`
2. `[Fix or improvement, affected file, and reason]`

Re-run the checks and add the final successful evidence. Do not claim a result that was not executed.
