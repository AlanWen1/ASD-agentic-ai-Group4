# Student 2 — Expense & Category Manager

## What's in here

```
student-2/
├── backend/            # Flask REST API + SQLite database (port 5000)
│   ├── app.py           CRUD endpoints + AI "suggest-category" endpoint
│   ├── database.py       SQLite connection/table setup
│   ├── seed_data.py      Populates ≥10 records in each table
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/test_app.py pytest tests used by CI
│
├── frontend/            # HTMX pages that call the backend API (port 5000 in-container)
│   ├── app.py
│   ├── templates/
│   ├── static/style.css
│   ├── requirements.txt
│   └── Dockerfile
│
└── docker-compose.student2.yml   # For testing YOUR module standalone
```

The GitHub Actions workflow lives at the repo root: `.github/workflows/student-2.yml`
(only triggers on changes inside `student-2/`).

## How to run it locally (before merging into the team's shared docker-compose.yml)

```bash
cd student-2
docker compose -f docker-compose.student2.yml up --build
```

First time only — pull the model into the running Ollama container:

```bash
docker exec -it $(docker ps -qf "ancestor=ollama/ollama:latest") ollama pull qwen2.5:0.5b
```

Then seed the database with sample data:

```bash
docker compose -f docker-compose.student2.yml exec backend python seed_data.py
```

Open the app: **http://localhost:5001**
Backend API directly: **http://localhost:5000/api/expenses**

## What to check works

1. Add an expense — it should appear in the table immediately (no page reload, that's HTMX).
2. Click "Suggest Category (AI)" after typing a description — it should call Ollama and show
   a suggested category next to the button. This is your AI integration requirement.
3. Delete an expense / category — row disappears immediately.
4. `/api/categories` and `/api/expenses` both return JSON with 10+ rows after seeding.

## Integrating into the team's shared setup

- Your `expenses` + `categories` tables are only used by this module — no other student's
  service should read/write them directly (per the "database per microservice" rule).
- The `OLLAMA_HOST` env var currently points at a local `ollama` service defined in
  `docker-compose.student2.yml`. In the team's shared root `docker-compose.yml`, point it at
  whatever the shared AI-mode service is called instead (e.g. `http://ai-mode:11434`) — check
  the `ai-services/ai-mode/` folder the team is building.
- Give your two Dockerfiles' service names (`backend`/`frontend`) a unique prefix if the team's
  shared compose file needs to avoid clashing with other students' service names, e.g.
  `student2-backend`, `student2-frontend`.

## Evidence to screenshot for the technical report

- The expense list with 10+ seeded records.
- The AI suggestion appearing after clicking the button (this is your "Plan → Act → Observe →
  Adapt" moment: you *plan* an expense, the AI *acts* by suggesting a category, you *observe*
  the suggestion, and *adapt* by accepting or overriding it).
- A green GitHub Actions run for `student-2.yml`.
- `docker compose -f docker-compose.student2.yml up` running successfully in a terminal.
