"""
Release 1: tests for the shared MCP / RAG integration routes
(/api/mcp/query, /api/rag/ask) on the expense backend.

These were previously untested — CI would stay green even if this
wiring silently broke, since nothing exercised it. Mirrors the mocking
style already used in test_auth.py (mock app.requests.request for the
current_user() auth check against finance-database).
"""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def _mock_auth_ok(user_id=1, username="alan"):
    """requests.request side_effect that approves any /sessions/<token> lookup
    (current_user()'s call to finance-database) with the given user."""
    def side_effect(method, url, **kwargs):
        if "/sessions/" in url:
            return MagicMock(ok=True, status_code=200, json=lambda: {"user": {"id": user_id, "username": username}})
        return MagicMock(ok=True, status_code=200, json=lambda: {})
    return side_effect


# ---------------------------------------------------------------------
# /api/mcp/query
# ---------------------------------------------------------------------

def test_mcp_query_without_token_rejected(client):
    resp = client.post("/api/mcp/query", json={"tool": "get_expenses"})
    assert resp.status_code == 401


@patch("app.requests.request")
def test_mcp_query_rejects_unknown_tool(mock_request, client):
    mock_request.side_effect = _mock_auth_ok()
    resp = client.post(
        "/api/mcp/query",
        json={"tool": "get_bills"},
        headers={"Authorization": "Bearer goodtoken"},
    )
    assert resp.status_code == 400
    assert "tool must be one of" in resp.get_json()["error"]


@patch("mcp_client.call_mcp_tool")
@patch("app.requests.request")
def test_mcp_query_returns_result_for_authenticated_user(mock_request, mock_call_tool, client):
    mock_request.side_effect = _mock_auth_ok(user_id=42)
    mock_call_tool.return_value = [{"id": 1, "name": "Groceries"}]

    resp = client.post(
        "/api/mcp/query",
        json={"tool": "get_categories"},
        headers={"Authorization": "Bearer goodtoken"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["tool"] == "get_categories"
    assert body["result"] == [{"id": 1, "name": "Groceries"}]
    # the authenticated user's own id must be what's forwarded to the MCP
    # tool -- not anything a client could try to pass in the request body
    mock_call_tool.assert_called_once_with("get_categories", user_id=42)


@patch("mcp_client.call_mcp_tool")
@patch("app.requests.request")
def test_mcp_query_empty_result_is_not_treated_as_an_error(mock_request, mock_call_tool, client):
    """Regression test: the mcp SDK returns zero content blocks (which
    mcp_client.py turns into `[]`) when a tool has no rows to return --
    that's a valid empty result, not a failure, so this must stay a 200."""
    mock_request.side_effect = _mock_auth_ok()
    mock_call_tool.return_value = []

    resp = client.post(
        "/api/mcp/query",
        json={"tool": "get_expenses"},
        headers={"Authorization": "Bearer goodtoken"},
    )

    assert resp.status_code == 200
    assert resp.get_json()["result"] == []


@patch("mcp_client.call_mcp_tool")
@patch("app.requests.request")
def test_mcp_query_propagates_mcp_server_error(mock_request, mock_call_tool, client):
    mock_request.side_effect = _mock_auth_ok()
    mock_call_tool.return_value = {"error": "Could not reach MCP server"}

    resp = client.post(
        "/api/mcp/query",
        json={"tool": "get_expenses"},
        headers={"Authorization": "Bearer goodtoken"},
    )

    assert resp.status_code == 502
    assert resp.get_json()["result"]["error"] == "Could not reach MCP server"


# ---------------------------------------------------------------------
# /api/rag/ask
# ---------------------------------------------------------------------

def test_rag_ask_without_token_rejected(client):
    resp = client.post("/api/rag/ask", json={"message": "hi"})
    assert resp.status_code == 401


@patch("app.requests.request")
def test_rag_ask_requires_a_message(mock_request, client):
    mock_request.side_effect = _mock_auth_ok()
    resp = client.post(
        "/api/rag/ask",
        json={"message": "   "},
        headers={"Authorization": "Bearer goodtoken"},
    )
    assert resp.status_code == 400


@patch("app.requests.post")
@patch("app.requests.request")
def test_rag_ask_forwards_question_and_returns_grounded_answer(mock_request, mock_post, client):
    mock_request.side_effect = _mock_auth_ok()
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "answer": "You spent $120 on Groceries this month.",
            "citations": ["expense#12", "expense#15"],
            "confidence_category": "high",
        },
    )

    resp = client.post(
        "/api/rag/ask",
        json={"message": "How much did I spend on groceries?"},
        headers={"Authorization": "Bearer goodtoken"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["answer"] == "You spent $120 on Groceries this month."
    assert body["confidence_category"] == "high"

    # confirm it actually forwarded the question to the shared RAG server
    called_url, = mock_post.call_args.args
    assert called_url.endswith("/answer_question")
    assert mock_post.call_args.kwargs["json"] == {"query": "How much did I spend on groceries?"}


@patch("app.requests.post")
@patch("app.requests.request")
def test_rag_ask_when_rag_server_unavailable(mock_request, mock_post, client):
    mock_request.side_effect = _mock_auth_ok()
    mock_post.side_effect = requests.exceptions.ConnectionError("refused")

    resp = client.post(
        "/api/rag/ask",
        json={"message": "How much did I spend on groceries?"},
        headers={"Authorization": "Bearer goodtoken"},
    )

    assert resp.status_code == 502
    assert "RAG server unavailable" in resp.get_json()["error"]
