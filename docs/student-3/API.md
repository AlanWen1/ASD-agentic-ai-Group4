# Student 3 API reference

The browser calls the frontend on port `3003`. The frontend proxies `/api/*` requests to the backend on port `5003`. The backend is the only service that calls the Database API on port `6003`.

## Authentication and user isolation

`GET /health` is public. Every `/api/*` endpoint requires the shared application session token in this header:

```http
Authorization: Bearer <session-token>
```

The authenticated request flow is:

1. The user signs in through the shared frontend on port `3000`.
2. The shared frontend opens Student 3 on port `3003` with the session token.
3. The Student 3 frontend forwards the `Authorization` header to its backend.
4. The backend validates the token through `finance-database:6000/sessions/{token}`.
5. The backend extracts the authenticated user ID and passes it to the Database API.
6. The Database API scopes every list, read, update, and delete operation to that user ID.

The browser must not choose or submit a `user_id`. The backend derives it from the validated session. A user therefore cannot read or change another user's income sources or pay schedules.

| Status | Meaning |
|---|---|
| `401` | The bearer token is missing, invalid, or expired |
| `503` | The shared authentication service is unavailable or returned an invalid response |

## Backend/API - port 5003

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend and Database API health; no token required |
| GET/POST | `/api/income-sources` | List or create the current user's income sources |
| GET/PUT/DELETE | `/api/income-sources/{id}` | Read, update, or delete one source owned by the current user |
| GET/POST | `/api/pay-schedules` | List or create the current user's schedules |
| GET/PUT/DELETE | `/api/pay-schedules/{id}` | Read, update, or delete one schedule owned by the current user |
| GET | `/api/dashboard?month=2026-08` | Deterministic monthly totals and schedule list for the current user |
| POST | `/api/pay-schedules/generate` | Generate expected dates from a source owned by the current user |
| GET | `/api/ai/status` | Check Ollama and configured model |
| POST | `/api/ai/analyse` | Generate one complete monthly AI analysis using the current user's data |
| POST | `/api/ai/chat` | Ask a free-form question about the current user's selected-month data |

### Create income source

```json
{
  "source_name": "UTS Student Assistant",
  "income_type": "Salary",
  "standard_amount": 920.00,
  "payment_frequency": "fortnightly",
  "active": true
}
```

Allowed frequencies: `weekly`, `fortnightly`, `monthly`, `quarterly`, `annually`, and `one-off`.

### Create pay schedule

```json
{
  "income_source_id": 1,
  "expected_pay_date": "2026-08-28",
  "expected_amount": 920.00,
  "received_date": null,
  "actual_amount": null,
  "status": "scheduled",
  "notes": "Expected fortnightly pay"
}
```

Allowed statuses: `scheduled`, `received`, `late`, and `cancelled`. A received payment requires both `received_date` and `actual_amount`.

### Generate expected dates

```json
{
  "income_source_id": 1,
  "start_date": "2026-09-11",
  "count": 3
}
```

### Ask the AI chat box

```json
{
  "message": "Which payments are still outstanding?",
  "month": "2026-08",
  "history": []
}
```

## Database API - port 6003

The Database API is an internal service. The backend supplies a positive `user_id` query parameter after validating the session token. Example internal requests are:

- `/api/income-sources?user_id=7&active=1&income_type=Salary&search=UTS`
- `/api/pay-schedules?user_id=7&month=2026-08&status=received&income_source_id=1`

Records belonging to other users are not returned. Browser clients and other features must call the Student 3 backend rather than selecting a `user_id` and calling the Database API directly. No service may open `student-3-income.db` directly.
