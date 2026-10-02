
"""
Release 1: Automated tests for Student 5 MCP and RAG integration.
Tests authentication, savings goal retrieval, user isolation,
RAG question forwarding, and error handling.
"""

import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests


# Load the Student 5 backend directly.
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)

sys.path.insert(0, BACKEND_DIR)

spec = importlib.util.spec_from_file_location(
    "student5_backend_mcp_rag", os.path.join(BACKEND_DIR, "app.py")
)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

backend.MCP_ENABLED = True
backend.RAG_ENABLED = True


@pytest.fixture
def client():
    backend.app.config["TESTING"] = True
    with backend.app.test_client() as test_client:
        yield test_client


def mock_auth(user_id=1):
    return MagicMock(
        status_code=200,
        json=lambda: {
            "user": {"id": user_id, "username": "testuser"}
        },
    )


AUTH_HEADER = {"Authorization": "Bearer testtoken"}


# ---------------------------------------------------------
# Backend MCP tests
# ---------------------------------------------------------

def test_mcp_requires_authentication(client):
    response = client.post("/mcp/query")

    assert response.status_code == 401


@patch("mcp_client.call_mcp_tool")
@patch.object(backend.requests, "get")
def test_mcp_returns_authenticated_users_goals(
    mock_get, mock_tool, client
):
    mock_get.return_value = mock_auth(user_id=42)

    mock_tool.return_value = [
        {
            "goal_id": 1,
            "user_id": 42,
            "goal_name": "New Laptop",
            "target_amount": 2000,
            "current_amount": 500,
        },
        {
            "goal_id": 2,
            "user_id": 99,
            "goal_name": "Holiday",
            "target_amount": 3000,
            "current_amount": 1000,
        },
    ]

    response = client.post(
        "/mcp/query",
        headers=AUTH_HEADER,
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["tool"] == "get_savings_goals"
    assert len(data["goals"]) == 1
    assert data["goals"][0]["goal_name"] == "New Laptop"

    mock_tool.assert_called_once_with(
        "get_savings_goals", user_id=42
    )


@patch("mcp_client.call_mcp_tool")
@patch.object(backend.requests, "get")
def test_mcp_empty_goals(mock_get, mock_tool, client):
    mock_get.return_value = mock_auth()
    mock_tool.return_value = []

    response = client.post(
        "/mcp/query",
        headers=AUTH_HEADER,
    )

    assert response.status_code == 200
    assert response.get_json()["goals"] == []


@patch("mcp_client.call_mcp_tool")
@patch.object(backend.requests, "get")
def test_mcp_server_error(mock_get, mock_tool, client):
    mock_get.return_value = mock_auth()
    mock_tool.return_value = {
        "error": "Could not reach MCP server"
    }

    response = client.post(
        "/mcp/query",
        headers=AUTH_HEADER,
    )

    assert response.status_code == 502
    assert "Could not reach MCP server" in response.get_json()["error"]


# ---------------------------------------------------------
# Backend RAG tests
# ---------------------------------------------------------

def test_rag_requires_authentication(client):
    response = client.post(
        "/rag/ask",
        json={"message": "How much have I saved?"},
    )

    assert response.status_code == 401


@patch.object(backend.requests, "get")
def test_rag_requires_question(mock_get, client):
    mock_get.return_value = mock_auth()

    response = client.post(
        "/rag/ask",
        json={"message": "   "},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 400


@patch.object(backend.requests, "post")
@patch.object(backend.requests, "get")
def test_rag_returns_grounded_answer(
    mock_get, mock_post, client
):
    mock_get.return_value = mock_auth()

    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "answer": "You have saved $500.",
            "citations": ["savings_goal#1"],
            "confidence_category": "high",
        },
    )

    response = client.post(
        "/rag/ask",
        json={"message": "How much have I saved?"},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["answer"] == "You have saved $500."
    assert data["confidence_category"] == "high"
    assert data["citations"] == ["savings_goal#1"]

    assert mock_post.call_args.args[0].endswith(
        "/answer_question"
    )
    assert mock_post.call_args.kwargs["json"] == {
        "query": "How much have I saved?"
    }


@patch.object(backend.requests, "post")
@patch.object(backend.requests, "get")
def test_rag_server_unavailable(mock_get, mock_post, client):
    mock_get.return_value = mock_auth()

    mock_post.side_effect = requests.exceptions.ConnectionError(
        "Connection refused"
    )

    response = client.post(
        "/rag/ask",
        json={"message": "How much have I saved?"},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 502
    assert "RAG server unavailable" in response.get_json()["error"]



# ---------------------------------------------------------
# Frontend MCP and RAG tests
# ---------------------------------------------------------

FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend")
)

frontend_spec = importlib.util.spec_from_file_location(
    "student5_frontend_mcp_rag",
    os.path.join(FRONTEND_DIR, "app.py"),
)
frontend = importlib.util.module_from_spec(frontend_spec)
frontend_spec.loader.exec_module(frontend)


@pytest.fixture
def frontend_client():
    frontend.app.config["TESTING"] = True
    with frontend.app.test_client() as test_client:
        yield test_client


def test_frontend_mcp_requires_authentication(frontend_client):
    with patch.object(frontend.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(status_code=401)

        response = frontend_client.post("/mcp-query")

    assert response.status_code == 200
    assert b"Authentication required" in response.data


def test_frontend_mcp_displays_savings_goals(frontend_client):
    with patch.object(frontend.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "tool": "get_savings_goals",
                "goals": [
                    {
                        "goal_name": "New Laptop",
                        "target_amount": 2000,
                        "current_amount": 500,
                    }
                ],
            },
        )

        response = frontend_client.post(
            "/mcp-query",
            headers=AUTH_HEADER,
        )

    assert response.status_code == 200
    assert b"New Laptop" in response.data
    assert b"2000.00" in response.data
    assert b"500.00" in response.data
    assert b'"goal_name"' not in response.data

    assert mock_post.call_args.kwargs["headers"] == AUTH_HEADER


def test_frontend_mcp_displays_empty_message(frontend_client):
    with patch.object(frontend.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "tool": "get_savings_goals",
                "goals": [],
            },
        )

        response = frontend_client.post(
            "/mcp-query",
            headers=AUTH_HEADER,
        )

    assert response.status_code == 200
    assert b"No savings goals found" in response.data


def test_frontend_mcp_displays_server_error(frontend_client):
    with patch.object(frontend.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(status_code=502)

        response = frontend_client.post(
            "/mcp-query",
            headers=AUTH_HEADER,
        )

    assert response.status_code == 200
    assert b"shared MCP server is unavailable" in response.data


def test_frontend_rag_requires_question(frontend_client):
    response = frontend_client.post(
        "/rag-ask",
        data={"rag_message": "   "},
    )

    assert response.status_code == 200
    assert b"Please enter a question" in response.data


def test_frontend_rag_displays_answer_and_citations(frontend_client):
    with patch.object(frontend.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "answer": "You have saved $500.",
                "citations": ["savings_goal#1"],
                "confidence_category": "high",
            },
        )

        response = frontend_client.post(
            "/rag-ask",
            data={"rag_message": "How much have I saved?"},
            headers=AUTH_HEADER,
        )

    assert response.status_code == 200
    assert b"You have saved $500." in response.data
    assert b"savings_goal#1" in response.data
    assert b"high" in response.data
    assert b'"citations"' not in response.data

    assert mock_post.call_args.kwargs["json"] == {
        "message": "How much have I saved?"
    }
    assert mock_post.call_args.kwargs["headers"] == AUTH_HEADER


def test_frontend_rag_displays_backend_error(frontend_client):
    with patch.object(frontend.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(status_code=502)

        response = frontend_client.post(
            "/rag-ask",
            data={"rag_message": "How much have I saved?"},
            headers=AUTH_HEADER,
        )

    assert response.status_code == 200
    assert b"Could not get a RAG response" in response.data

