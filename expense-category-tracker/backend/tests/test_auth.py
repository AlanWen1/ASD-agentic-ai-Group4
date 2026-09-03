import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_categories_without_token_rejected(client):
    resp = client.get("/api/categories")
    assert resp.status_code == 401


@patch("app.requests.request")
def test_categories_with_invalid_token_rejected(mock_request, client):
    mock_request.return_value = MagicMock(ok=False, status_code=401)
    resp = client.get("/api/categories", headers={"Authorization": "Bearer badtoken"})
    assert resp.status_code == 401


@patch("app.requests.request")
def test_categories_with_valid_token_forwards(mock_request, client):
    def side_effect(method, url, **kwargs):
        if "/sessions/" in url:
            return MagicMock(ok=True, status_code=200, json=lambda: {"user": {"id": 1, "username": "alan"}})
        return MagicMock(ok=True, status_code=200, json=lambda: [{"id": 1, "name": "Groceries"}])
    mock_request.side_effect = side_effect
    resp = client.get("/api/categories", headers={"Authorization": "Bearer goodtoken"})
    assert resp.status_code == 200
    assert resp.get_json()[0]["name"] == "Groceries"


@patch("app.requests.request")
def test_categories_forwards_current_users_id_to_database(mock_request, client):
    """The user-isolation fix: expense-backend must tell expense-database
    which user is asking, on every category/expense call."""
    calls = []

    def side_effect(method, url, **kwargs):
        if "/sessions/" in url:
            return MagicMock(ok=True, status_code=200, json=lambda: {"user": {"id": 42, "username": "alan"}})
        calls.append((method, url, kwargs.get("params")))
        return MagicMock(ok=True, status_code=200, json=lambda: [])

    mock_request.side_effect = side_effect
    client.get("/api/categories", headers={"Authorization": "Bearer goodtoken"})
    client.get("/api/expenses", headers={"Authorization": "Bearer goodtoken"})

    database_calls = [c for c in calls if "/categories" in c[1] or "/expenses" in c[1]]
    assert database_calls, "expected at least one call to expense-database"
    for _, _, params in database_calls:
        assert params.get("user_id") == 42


def test_suggest_category_requires_auth(client):
    resp = client.post("/api/expenses/suggest-category", json={"description": "coffee"})
    assert resp.status_code == 401


def test_assistant_requires_auth(client):
    resp = client.post("/api/expenses/assistant", json={"message": "hi"})
    assert resp.status_code == 401


@patch("app.requests.request")
@patch("app.run_agent_loop")
def test_assistant_runs_agent_loop_for_authenticated_user(mock_run_agent_loop, mock_request, client):
    mock_request.return_value = MagicMock(
        ok=True, status_code=200, json=lambda: {"user": {"id": 7, "username": "alan"}}
    )
    mock_run_agent_loop.return_value = {
        "answer": "You have 3 expenses this month.",
        "trace": [{"step": 0, "type": "tool_call", "tool": "get_expenses", "args": {}}],
    }

    resp = client.post(
        "/api/expenses/assistant",
        json={"message": "How many expenses do I have?"},
        headers={"Authorization": "Bearer goodtoken"},
    )

    assert resp.status_code == 200
    assert resp.get_json()["answer"] == "You have 3 expenses this month."
    mock_run_agent_loop.assert_called_once_with("How many expenses do I have?", 7)


def test_assistant_requires_a_message(client):
    with patch("app.requests.request") as mock_request:
        mock_request.return_value = MagicMock(ok=True, status_code=200, json=lambda: {"user": {"id": 1}})
        resp = client.post(
            "/api/expenses/assistant", json={}, headers={"Authorization": "Bearer goodtoken"}
        )
    assert resp.status_code == 400
