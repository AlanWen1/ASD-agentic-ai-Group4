"""
Release 1: MCP + RAG integration tests for Student 1 (Budget Manager).

Runs against the real services, the same way test_budget_api.py does:
  - finance-database  (auth)      http://localhost:6000
  - budget-backend                http://localhost:5001
  - MCP server (host process)     http://localhost:5100/mcp
  - RAG server (host process)     http://localhost:5101

No LLM is needed, so these run in CI.
"""

import os
import sys

import pytest
import requests

BASE_URL = "http://localhost:5001/api"
AUTH_URL = "http://localhost:6000"
RAG_URL = os.environ.get("RAG_SERVER_URL", "http://localhost:5101").rstrip("/")

# Use the backend's own MCP client so the tests exercise the same code path.
# Must be set before import: mcp_client reads MCP_SERVER_URL at import time.
os.environ.setdefault("MCP_SERVER_URL", "http://localhost:5100/mcp")
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, BACKEND_DIR)
from mcp_client import call_mcp_tool  # noqa: E402


# ---------------------------------------------------------------------------
# Auth helpers (own users, so these tests don't interfere with test_budget_api)
# ---------------------------------------------------------------------------

MCP_USER = {
    "username": "pytest_mcp_user",
    "email": "pytest_mcp@test.com",
    "password": "pytest_password_789",
}
MCP_OTHER_USER = {
    "username": "pytest_mcp_other",
    "email": "pytest_mcp_other@test.com",
    "password": "pytest_password_012",
}


def _login(user):
    resp = requests.post(
        f"{AUTH_URL}/auth/login",
        json={"identifier": user["username"], "password": user["password"]},
    )
    if resp.status_code != 200:
        reg = requests.post(f"{AUTH_URL}/users", json=user)
        assert reg.status_code in (201, 409), f"Could not create user: {reg.text}"
        resp = requests.post(
            f"{AUTH_URL}/auth/login",
            json={"identifier": user["username"], "password": user["password"]},
        )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["token"]

    session = requests.get(f"{AUTH_URL}/sessions/{token}")
    assert session.status_code == 200, f"Session lookup failed: {session.text}"
    user_id = session.json()["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, user_id


@pytest.fixture(scope="module")
def user():
    return _login(MCP_USER)


@pytest.fixture(scope="module")
def other_user():
    return _login(MCP_OTHER_USER)


@pytest.fixture(scope="module")
def seeded(user):
    """Create two active budgets for the test user (one with categories 300 + 100).
    Deleted again after the module finishes."""
    headers, _ = user
    created = []
    for month in (10, 11):
        resp = requests.post(
            f"{BASE_URL}/budgets",
            json={"month": month, "year": 2030, "status": "active"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        created.append(resp.json()["budget_id"])

    main_id = created[0]
    for name, amount in (("Rent", 300.0), ("Food", 100.0)):
        resp = requests.post(
            f"{BASE_URL}/budgets/{main_id}/categories",
            json={"category_name": name, "allocated_amount": amount},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    yield {"budget_ids": created, "main_id": main_id}

    for budget_id in created:
        requests.delete(f"{BASE_URL}/budgets/{budget_id}", headers=headers)


def _overview_budgets(result):
    """Accept either a bare list or {"budgets": [...]} from get_budget_overview."""
    assert not (isinstance(result, dict) and "error" in result), result
    if isinstance(result, dict) and "budgets" in result:
        return result["budgets"]
    assert isinstance(result, list), f"Unexpected overview shape: {result}"
    return result


def _find_budget(budgets, budget_id):
    for b in budgets:
        if b.get("budget_id") == budget_id:
            return b
    pytest.fail(f"budget {budget_id} not in overview: {budgets}")


# ---------------------------------------------------------------------------
# RAG server
# ---------------------------------------------------------------------------

def test_rag_health_corpus_loaded():
    resp = requests.get(f"{RAG_URL}/health", timeout=10)
    assert resp.status_code == 200
    assert resp.json().get("corpus_loaded") is True


def test_rag_retrieve_context_returns_chunks():
    resp = requests.post(
        f"{RAG_URL}/retrieve_context",
        json={"query": "How should I split my monthly budget?"},
        timeout=30,
    )
    assert resp.status_code == 200
    assert resp.json(), "retrieve_context returned an empty response"


# ---------------------------------------------------------------------------
# MCP server (called directly, as the agent does)
# ---------------------------------------------------------------------------

def test_mcp_get_budgets_returns_full_list(user, seeded):
    """Regression test for the first-item bug: all budgets must come back."""
    _, user_id = user
    result = call_mcp_tool("get_budgets", user_id=user_id)
    assert isinstance(result, list), result
    returned_ids = {b["budget_id"] for b in result}
    for budget_id in seeded["budget_ids"]:
        assert budget_id in returned_ids


def test_mcp_overview_totals(user, seeded):
    _, user_id = user
    result = call_mcp_tool("get_budget_overview", user_id=user_id, status="active")
    budget = _find_budget(_overview_budgets(result), seeded["main_id"])
    assert budget["total_allocated"] == pytest.approx(400.0)
    assert len(budget["categories"]) == 2


def test_mcp_overview_percentages_sum_to_100(user, seeded):
    _, user_id = user
    result = call_mcp_tool("get_budget_overview", user_id=user_id, status="active")
    budget = _find_budget(_overview_budgets(result), seeded["main_id"])
    shares = {c["category_name"]: c["share_pct"] for c in budget["categories"]}
    assert sum(shares.values()) == pytest.approx(100.0, abs=0.5)
    assert shares["Rent"] == pytest.approx(75.0, abs=0.5)


def test_mcp_overview_user_isolation(other_user, seeded):
    _, other_id = other_user
    result = call_mcp_tool("get_budget_overview", user_id=other_id, status="active")
    other_ids = {b.get("budget_id") for b in _overview_budgets(result)}
    for budget_id in seeded["budget_ids"]:
        assert budget_id not in other_ids


# ---------------------------------------------------------------------------
# Backend MCP routes (frontend -> backend container -> MCP server)
# ---------------------------------------------------------------------------

def test_backend_mcp_query_with_auth(user, seeded):
    headers, _ = user
    resp = requests.post(f"{BASE_URL}/mcp/query", headers=headers, timeout=30)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tool"] == "get_budgets"
    returned_ids = {b["budget_id"] for b in data["result"]}
    assert set(seeded["budget_ids"]) <= returned_ids


def test_backend_mcp_overview_with_auth(user, seeded):
    headers, _ = user
    resp = requests.post(f"{BASE_URL}/mcp/overview", headers=headers, timeout=30)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tool"] == "get_budget_overview"
    _find_budget(_overview_budgets(data["result"]), seeded["main_id"])


def test_backend_mcp_query_requires_auth():
    resp = requests.post(f"{BASE_URL}/mcp/query", timeout=10)
    assert resp.status_code == 401


def test_backend_mcp_overview_requires_auth():
    resp = requests.post(f"{BASE_URL}/mcp/overview", timeout=10)
    assert resp.status_code == 401