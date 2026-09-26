"""
MCP server tools — Release 1 requirement.

Each function here is a thin, read-only forwarder to one of the team's
five existing Database APIs (the same services each module's own backend
already calls). Nothing here writes data or duplicates business logic —
it just gives the shared MCP server (see server.py) something real to
expose as tools, instead of inventing a parallel data layer.

Every underlying service is a Docker container whose port is published to
the host (see docker-compose.yml's `ports:` entries), and this MCP server
itself runs as a local, non-containerised host process (see
../ai-mode/README.md for why: the same Release 1 requirement applies here).
That means these functions talk to `localhost:<port>`, not
`host.docker.internal` or a Docker-network service name — this process
isn't inside a container, so neither of those would resolve.

Each database's own real auth convention is preserved rather than
invented: expense-category-tracker, bill-tracker, and student-3 all
require a `user_id` query parameter (see each database's app.py); the
Budget Manager's `budget-backend` instead requires an `X-User-Id` header
(see student-1-budget/backend/app.py's get_user_id()); the Savings Goal
Manager's `/goals` endpoint does not filter by user at all in the current
implementation (see student-5/database/app.py) — get_savings_goals()
documents this rather than pretending otherwise.

Every function returns a JSON-serialisable dict or list on success, or a
structured `{"error": "..."}` dict on failure — never raises — so a
caller (the MCP tool wrappers in server.py, or a backend's own route)
never has to wrap these in a try/except to get a safe result to show a
user.
"""
import os

import requests

EXPENSE_DB_URL = os.environ.get("EXPENSE_DB_URL", "http://localhost:6002").rstrip("/")
BILL_DB_URL = os.environ.get("BILL_DB_URL", "http://localhost:6004").rstrip("/")
INCOME_DB_URL = os.environ.get("INCOME_DB_URL", "http://localhost:6003").rstrip("/")
SAVINGS_DB_URL = os.environ.get("SAVINGS_DB_URL", "http://localhost:6005").rstrip("/")
BUDGET_DB_URL = os.environ.get("BUDGET_DB_URL", "http://localhost:6001").rstrip("/")

DEFAULT_TIMEOUT = int(os.environ.get("MCP_TOOL_TIMEOUT", "10"))


def _get(base_url, path, *, params=None, headers=None):
    """Shared GET helper: never raises, always returns a JSON-serialisable
    dict or list. Mirrors the structured-error convention used by
    ai-services/ai-mode/service.py's _proxy()."""
    try:
        response = requests.get(
            f"{base_url}{path}", params=params, headers=headers, timeout=DEFAULT_TIMEOUT
        )
    except requests.RequestException as exc:
        return {"error": f"Could not reach {base_url}{path}: {exc}"}
    try:
        body = response.json()
    except ValueError:
        return {"error": f"{base_url}{path} returned a non-JSON response", "status_code": response.status_code}
    if response.status_code >= 400:
        return {"error": body.get("error", f"Request to {path} failed"), "status_code": response.status_code}
    return body


def _require_user_id(user_id):
    if user_id is None or (isinstance(user_id, str) and not user_id.strip()):
        return {"error": "user_id is required"}
    return None


# ---------------------------------------------------------------------
# Expense & Category Manager (Student 2) — expense-database, port 6002
# ---------------------------------------------------------------------

def get_expenses(user_id, category_id=None):
    """List a user's expenses, optionally filtered by category_id.
    Forwards to GET /expenses on the expense-category-tracker database."""
    error = _require_user_id(user_id)
    if error:
        return error
    params = {"user_id": user_id}
    if category_id is not None:
        params["category_id"] = category_id
    return _get(EXPENSE_DB_URL, "/expenses", params=params)


def get_categories(user_id):
    """List a user's expense categories.
    Forwards to GET /categories on the expense-category-tracker database."""
    error = _require_user_id(user_id)
    if error:
        return error
    return _get(EXPENSE_DB_URL, "/categories", params={"user_id": user_id})


# ---------------------------------------------------------------------
# Bill Manager (Student 4) — bill-database, port 6004
# ---------------------------------------------------------------------

def get_bills(user_id):
    """List a user's bills. Forwards to GET /bills on the bill-tracker database."""
    error = _require_user_id(user_id)
    if error:
        return error
    return _get(BILL_DB_URL, "/bills", params={"user_id": user_id})


def get_bills_summary(user_id):
    """Total/pending bill amounts and overdue count for a user.
    Forwards to GET /summary on the bill-tracker database."""
    error = _require_user_id(user_id)
    if error:
        return error
    return _get(BILL_DB_URL, "/summary", params={"user_id": user_id})


# ---------------------------------------------------------------------
# Income & Pay Schedule Manager (Student 3) — student-3-database, port 6003
# ---------------------------------------------------------------------

def get_income_sources(user_id):
    """List a user's income sources.
    Forwards to GET /api/income-sources on the student-3 database."""
    error = _require_user_id(user_id)
    if error:
        return error
    return _get(INCOME_DB_URL, "/api/income-sources", params={"user_id": user_id})


def get_pay_schedules(user_id):
    """List a user's pay schedules.
    Forwards to GET /api/pay-schedules on the student-3 database."""
    error = _require_user_id(user_id)
    if error:
        return error
    return _get(INCOME_DB_URL, "/api/pay-schedules", params={"user_id": user_id})


# ---------------------------------------------------------------------
# Savings Goal Manager (Student 5) — savings-database, port 6005
# ---------------------------------------------------------------------

def get_savings_goals(user_id=None):
    """List savings goals.

    Note: the current savings-database implementation's GET /goals does
    not filter by user (see student-5/database/app.py) — it returns every
    goal in the database regardless of who asks. `user_id` is accepted
    here for a consistent tool signature and forward-compatibility, but is
    NOT sent upstream because the upstream endpoint has no such parameter;
    this is a known, pre-existing data-isolation gap in that module, not
    something this tool should silently mask by pretending to filter.
    """
    return _get(SAVINGS_DB_URL, "/goals")


# ---------------------------------------------------------------------
# Budget Manager (Student 1) — budget-backend itself, port 5001
# (no standalone database service: budget-backend reads its SQLite file
# directly, so this calls the backend's own API instead of a database API)
# ---------------------------------------------------------------------

def get_budgets(user_id):
    """List a user's budgets.
    Forwards to GET /api/budgets on budget-database with ?user_id=
    — same convention as every other module's database tool."""
    error = _require_user_id(user_id)
    if error:
        return error
    return _get(BUDGET_DB_URL, "/api/budgets", params={"user_id": user_id})



if __name__ == "__main__":
    import json

    for name, result in [
        ("get_expenses(1)", get_expenses(1)),
        ("get_categories(1)", get_categories(1)),
        ("get_bills(1)", get_bills(1)),
        ("get_bills_summary(1)", get_bills_summary(1)),
        ("get_income_sources(1)", get_income_sources(1)),
        ("get_pay_schedules(1)", get_pay_schedules(1)),
        ("get_savings_goals()", get_savings_goals()),
        ("get_budgets(1)", get_budgets(1)),

    ]:
        print(f"--- {name} ---")
        print(json.dumps(result, indent=2, default=str))
