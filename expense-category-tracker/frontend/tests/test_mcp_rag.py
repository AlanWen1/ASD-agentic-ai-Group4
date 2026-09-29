"""
Release 1: tests for the frontend's /mcp-query and /rag-ask routes,
which proxy to this module's backend (/api/mcp/query, /api/rag/ask)
and render the result as readable text -- not raw JSON -- per the
team's UX requirement. Previously untested.
"""
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


def _signed_in(client, token="abc123"):
    with client.session_transaction() as sess:
        sess["finance_token"] = token


# ---------------------------------------------------------------------
# /mcp-query
# ---------------------------------------------------------------------

def test_mcp_query_requires_sign_in(client):
    resp = client.post("/mcp-query", data={"tool": "get_categories"})
    assert resp.status_code == 200
    assert b"Sign in required" in resp.data


@patch("app.requests.post")
def test_mcp_query_renders_categories_as_readable_text(mock_post, client):
    _signed_in(client)
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "tool": "get_categories",
            "result": [{"id": 1, "name": "Groceries"}, {"id": 2, "name": "Dining"}],
        },
    )

    resp = client.post("/mcp-query", data={"tool": "get_categories"})

    assert resp.status_code == 200
    assert b"Groceries" in resp.data
    assert b"Dining" in resp.data
    # must be plain text, not a raw JSON/array dump
    assert b'"id"' not in resp.data
    assert b"[{" not in resp.data


@patch("app.requests.post")
def test_mcp_query_renders_expenses_as_readable_text(mock_post, client):
    _signed_in(client)
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "tool": "get_expenses",
            "result": [
                {
                    "date": "2026-09-20",
                    "description": "Woolworths",
                    "amount": 45.5,
                    "category_name": "Groceries",
                }
            ],
        },
    )

    resp = client.post("/mcp-query", data={"tool": "get_expenses"})

    assert resp.status_code == 200
    assert b"Woolworths" in resp.data
    assert b"45.50" in resp.data
    assert b"Groceries" in resp.data
    assert b'"amount"' not in resp.data


@patch("app.requests.post")
def test_mcp_query_shows_empty_state_message(mock_post, client):
    _signed_in(client)
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"tool": "get_expenses", "result": []},
    )

    resp = client.post("/mcp-query", data={"tool": "get_expenses"})

    assert resp.status_code == 200
    assert b"you have no expenses yet" in resp.data
    assert b"[]" not in resp.data


@patch("app.requests.post")
def test_mcp_query_shows_backend_error_as_text(mock_post, client):
    _signed_in(client)
    mock_post.return_value = MagicMock(
        status_code=502,
        json=lambda: {"tool": "get_expenses", "result": {"error": "Could not reach MCP server"}},
    )

    resp = client.post("/mcp-query", data={"tool": "get_expenses"})

    assert resp.status_code == 200
    assert b"Could not reach MCP server" in resp.data


@patch("app.requests.post")
def test_mcp_query_expired_session_shows_gate(mock_post, client):
    _signed_in(client)
    mock_post.return_value = MagicMock(status_code=401)

    resp = client.post("/mcp-query", data={"tool": "get_expenses"})

    assert resp.status_code == 200
    assert b"Sign in required" in resp.data
    with client.session_transaction() as sess:
        assert "finance_token" not in sess


# ---------------------------------------------------------------------
# /rag-ask
# ---------------------------------------------------------------------

def test_rag_ask_requires_sign_in(client):
    resp = client.post("/rag-ask", data={"rag_message": "How much did I spend?"})
    assert resp.status_code == 200
    assert b"Sign in required" in resp.data


def test_rag_ask_requires_a_message(client):
    _signed_in(client)
    resp = client.post("/rag-ask", data={"rag_message": "   "})
    assert resp.status_code == 200
    assert b"Please enter a question" in resp.data


@patch("app.requests.post")
def test_rag_ask_renders_answer_with_citations_as_text(mock_post, client):
    _signed_in(client)
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "answer": "You spent $120 on Groceries this month.",
            "citations": ["expense#12", "expense#15"],
            "confidence_category": "high",
        },
    )

    resp = client.post("/rag-ask", data={"rag_message": "How much did I spend on groceries?"})

    assert resp.status_code == 200
    assert b"You spent $120 on Groceries this month." in resp.data
    assert b"high" in resp.data
    assert b"expense#12" in resp.data
    assert b'"citations"' not in resp.data


@patch("app.requests.post")
def test_rag_ask_shows_error_from_backend(mock_post, client):
    _signed_in(client)
    mock_post.return_value = MagicMock(
        status_code=502,
        json=lambda: {"error": "RAG server unavailable: refused"},
    )

    resp = client.post("/rag-ask", data={"rag_message": "How much did I spend?"})

    assert resp.status_code == 200
    assert b"RAG server unavailable" in resp.data
