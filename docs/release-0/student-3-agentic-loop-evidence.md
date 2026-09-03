# Student 3 agentic loop evidence - shared authentication integration

This file records Yongjian Zhou's module contribution to the team's agentic loop. The team report should combine this evidence with the second selected module. It does not claim that Student 3 alone is the complete team loop.

## PLAN

### Baseline

The independent Income & Pay Schedule Manager already provided frontend, backend, Database API, SQLite CRUD, deterministic calculations, Docker configuration, tests, and Ollama/Qwen chat. The baseline test suite reported:

```text
10 passed in 0.40s
```

However, passing isolated tests did not prove that the module was safely integrated with the shared application. The module still needed to use the shared session token and isolate each user's records.

### Improvement goal

Integrate Student 3 with the shared authentication service so that:

- the shared home page can open the module while preserving the session token;
- every Student 3 `/api/*` request requires a valid bearer token;
- the backend derives the user ID from the validated session;
- the Database API scopes every CRUD and dashboard query to that user ID;
- one user cannot read, update, or delete another user's records;
- authentication failures return clear `401` or `503` responses; and
- automated tests cover the new authentication and isolation behaviour.

### AI prompt objective

The AI-assisted development request was to review the existing Student 3 three-service implementation and integrate it with the team's shared authentication service without breaking its independent frontend, backend, Database API, CRUD, AI, or Docker responsibilities. The request also required tests for missing tokens, authenticated requests, and cross-user data isolation.

This is a truthful summary of the development objective, not a verbatim transcript. The original chat or screenshot should be retained separately if the final report requires the exact prompt.

## ACT

The following changes were implemented:

- Added shared navigation and Student 3 services to the team application and root `docker-compose.yml`.
- Updated `student-3/frontend/app.py` and `student-3/frontend/static/app.js` to receive and forward the bearer token.
- Updated `student-3/backend/app.py` to validate the token through `finance-database:6000/sessions/{token}` and derive the authenticated user ID.
- Updated `student-3/database/app.py` so list, read, create, update, delete, dashboard, and generated-schedule operations are scoped by `user_id`.
- Expanded backend, Database API, and frontend tests to cover authentication and user isolation.

### Commit and pull-request evidence

- Initial Student 3 implementation: commit `1a56544`.
- Shared navigation integration: commit `82ba842`.
- Authentication and isolation implementation: commit `2a00ff8`.
- Authentication pull request: [PR #5](https://github.com/AlanWen1/ASD-agentic-ai-Group4/pull/5).
- Authentication merge commit on `main`: `250f8a0`.

## OBSERVE

### Baseline observation

```text
py -m pytest -q .\student-3\tests
10 passed in 0.40s
```

The baseline tests confirmed that the independent module worked, but they did not demonstrate shared authentication or cross-user isolation.

### Observation after implementation

```text
py -m pytest -q .\student-3\tests
13 passed in 0.45s

docker compose config --quiet
Exit code 0 (no output)
```

Manual integration evidence captured during testing showed:

- the shared sign-in page at `http://localhost:3000`;
- the shared home page displaying the Income & Pay Schedule Manager card;
- navigation to `http://localhost:3003/?token=...`;
- the Student 3 dashboard loading after authenticated navigation; and
- the Student 3 test suite completing successfully.

### Issues identified

1. The isolated baseline did not enforce the team's shared session on Student 3 API routes.
2. Income sources and pay schedules needed ownership filtering so authenticated users could not access each other's records.
3. The original ten tests did not provide direct evidence for the new authentication and isolation requirements.

## ADAPT

The implementation was adapted in response to those observations:

1. Added bearer-token validation and explicit `401` and `503` responses in the backend.
2. Removed client control over record ownership by deriving `user_id` from the validated shared session.
3. Added `user_id` conditions to Database API queries and mutations so cross-user resources behave as not found.
4. Forwarded authentication through the Student 3 frontend proxy.
5. Added authentication and isolation tests, increasing the verified suite from 10 to 13 passing tests.

An additional post-integration review found that the Student 3 green theme was inconsistent with the shared blue interface. The CSS was aligned with the shared theme in commit `afe65f0` and merged through [PR #8](https://github.com/AlanWen1/ASD-agentic-ai-Group4/pull/8).

## Final verification before submission

Run these checks again from the repository root and retain screenshots or terminal output:

```powershell
py -m pytest -q .\student-3\tests
py -m compileall -q .\student-3
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Only record Docker services as healthy after the final `docker compose ps` output confirms their state.
