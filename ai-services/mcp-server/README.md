# MCP Server

Release 1 requirement (see project spec section 4.2): one shared,
**non-containerised** local Model Context Protocol server, used by all
five student features.

**Current state:** implemented. `server.py` uses the official `mcp`
Python SDK (2.x — `MCPServer`, formerly `FastMCP` in 1.x) over Streamable
HTTP, exposing 8 read-only tools that forward to each module's existing
Database API (or, for Budget Manager, its backend directly — see below).
No database is duplicated and no business logic is reimplemented; every
tool is a thin, structured-error-returning wrapper — see `tools.py`'s
module docstring for the full rationale and each database's own auth
convention.

## Run it

```bash
./run_local.sh
```

or directly:

```bash
pip install -r requirements.txt
python3 server.py
```

Starts a local host process listening on `http://localhost:5100/mcp`
(Streamable HTTP transport). **Start this before `docker compose up`**,
same as `../ai-mode/run_local.sh` — this must NOT be added to
`docker-compose.yml` as a service (Release 1 requires AI-Mode, the MCP
server, the RAG server, and the agentic loop to all be non-containerised).

## Tools

| Tool | Module | Input | Forwards to |
| --- | --- | --- | --- |
| `get_expenses` | Expense & Category Manager | `user_id`, `category_id?` | `GET /expenses` on expense-database (:6002) |
| `get_categories` | Expense & Category Manager | `user_id` | `GET /categories` on expense-database (:6002) |
| `get_bills` | Bill Manager | `user_id` | `GET /bills` on bill-database (:6004) |
| `get_bills_summary` | Bill Manager | `user_id` | `GET /summary` on bill-database (:6004) |
| `get_income_sources` | Income & Pay Schedule Manager | `user_id` | `GET /api/income-sources` on student-3-database (:6003) |
| `get_pay_schedules` | Income & Pay Schedule Manager | `user_id` | `GET /api/pay-schedules` on student-3-database (:6003) |
| `get_savings_goals` | Savings Goal Manager | none (see note) | `GET /goals` on savings-database (:6005) |
| `get_budgets` | Budget Manager | `user_id` | `GET /api/budgets` on budget-backend (:5001) |

Notes:
- Every underlying service's port is published to the host in
  `docker-compose.yml`, so this process (running on the host, not in a
  container) reaches them at `localhost:<port>`.
- `get_savings_goals` does not filter by user because the current
  `student-5/database/app.py` `GET /goals` endpoint doesn't accept a
  user filter — a pre-existing data-isolation gap in that module, not
  something masked here.
- `get_budgets` sends `X-User-Id` as a header, not a query parameter,
  because that's what `student-1-budget/backend/app.py`'s own
  `get_user_id()` requires — a different (also legitimate) convention
  from the other four modules, left as-is.

## Testing

```bash
python3 -m pytest tests/ -q          # 13 tests, all mocked — no live services needed
python3 tools.py                     # calls every tool once against whatever's running locally
```

## Wiring into a feature (in progress)

Each backend is expected to call this server through its own backend/API
(an MCP client), not directly from the frontend — see the project spec's
"MCP Request Flow" requirement. That client-side wiring is being added
per-module, starting with Expense & Category Manager as the reference
implementation.
