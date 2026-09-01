# Student 3 API reference

The browser calls the frontend on port `3003`. The frontend proxies `/api/*` requests to the backend on port `5003`. The backend is the only service that calls the Database API on port `6003`.

## Backend/API - port 5003

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend and Database API health |
| GET/POST | `/api/income-sources` | List or create income sources |
| GET/PUT/DELETE | `/api/income-sources/{id}` | Read, update, or delete one source |
| GET/POST | `/api/pay-schedules` | List or create schedules |
| GET/PUT/DELETE | `/api/pay-schedules/{id}` | Read, update, or delete one schedule |
| GET | `/api/dashboard?month=2026-08` | Deterministic monthly totals and schedule list |
| POST | `/api/pay-schedules/generate` | Generate expected dates from a source frequency |
| GET | `/api/ai/status` | Check Ollama and configured model |
| POST | `/api/ai/analyse` | Generate one complete monthly AI analysis |
| POST | `/api/ai/chat` | Ask a free-form question about selected-month data |

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

The Database API exposes the two CRUD resources used above. Query filters include:

- `/api/income-sources?active=1&income_type=Salary&search=UTS`
- `/api/pay-schedules?month=2026-08&status=received&income_source_id=1`

Other features must use these HTTP endpoints and must not open `student-3-income.db` directly.
