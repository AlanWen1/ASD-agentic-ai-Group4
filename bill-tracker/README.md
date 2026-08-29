# Bill Tracker — Flask Microservices + SQLite + Ollama

A small bill-tracking microservice application with CRUD operations and a local AI assistant powered by Ollama `qwen2.5:0.5b`.

## Architecture

- **Frontend**: Flask server + HTML/CSS/JavaScript — `localhost:3004`
- **Backend**: Flask REST API + Ollama integration — `localhost:5004`
- **Database**: Flask database microservice backed by a persistent SQLite file — `localhost:6004`
- **AI**: Existing local Ollama service, expected on `localhost:11434`

### Important SQLite note
SQLite itself is an embedded database and does **not** listen on TCP port 6004. To satisfy the requested separate database service/port, this project runs a small Flask HTTP wrapper around the SQLite file. Port **6004** is therefore the **database service API**, not a SQLite network listener.

## Run with Docker

From this directory:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:3004
```

The services are available at:

```text
Frontend:  http://localhost:3004
Backend:   http://localhost:5004
Database:  http://localhost:6004
```

## Ollama setup

Make sure Ollama is running on the host and the model is installed:

```bash
ollama pull qwen2.5:0.5b
ollama list
```

The backend container uses:

```text
http://host.docker.internal:11434
```

This is suitable for Docker Desktop on Windows/macOS and is also configured for Linux with `host-gateway` in `docker-compose.yml`.

If Ollama is running somewhere else, change `OLLAMA_URL` in `docker-compose.yml`.

## API endpoints

### Backend

- `GET /health`
- `GET /bills`
- `POST /bills`
- `GET /bills/<id>`
- `PUT /bills/<id>`
- `DELETE /bills/<id>`
- `GET /summary`
- `POST /chat`

Example bill payload:

```json
{
  "name": "Internet",
  "amount": 79.95,
  "due_date": "2026-09-10",
  "frequency": "Monthly",
  "status": "Pending"
}
```

Allowed frequencies: `Weekly`, `Monthly`, `Quarterly`, `Yearly`, `One-time`.

Allowed statuses: `Pending`, `Paid`, `Overdue`.

### Database service

The database service mirrors the bill CRUD routes directly and stores the data in `/data/bills.db`. The Docker named volume `bill_data` keeps it persistent when containers are recreated.

## Local development without Docker

You can also run each service independently with Python 3.12+.

Database:

```bash
cd database
pip install -r requirements.txt
python app.py
```

Backend:

```bash
cd backend
pip install -r requirements.txt
set DATABASE_URL=http://localhost:6004
set OLLAMA_URL=http://localhost:11434
python app.py
```

Frontend:

```bash
cd frontend
pip install -r requirements.txt
set BACKEND_URL=http://localhost:5004
python app.py
```

On PowerShell, use `$env:NAME="value"` instead of `set NAME=value`.

## Data model

Each bill contains:

- `id`
- `name`
- `amount`
- `due_date`
- `frequency`
- `status`
- `created_at`
- `updated_at`
