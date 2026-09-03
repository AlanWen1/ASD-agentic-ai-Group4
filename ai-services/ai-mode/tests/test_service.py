import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@patch("ollama_client.requests.get")
def test_health_ok_when_ollama_reachable(mock_get, client):
    mock_get.return_value = MagicMock(ok=True)

    resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "ai-mode"
    assert data["ollama"] is True


@patch("ollama_client.requests.get")
def test_health_degraded_when_ollama_unreachable(mock_get, client):
    import ollama_client
    mock_get.side_effect = ollama_client.requests.RequestException("connection refused")

    resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.get_json()["status"] == "degraded"


@patch("ollama_client.requests.request")
def test_generate_proxies_to_native_ollama_api(mock_request, client):
    mock_request.return_value = MagicMock(
        status_code=200, json=lambda: {"response": "Groceries"}
    )

    resp = client.post("/api/generate", json={"model": "qwen2.5:0.5b", "prompt": "classify: coffee"})

    assert resp.status_code == 200
    assert resp.get_json() == {"response": "Groceries"}
    method, url = mock_request.call_args.args
    assert method == "POST"
    assert url.endswith("/api/generate")


@patch("ollama_client.requests.request")
def test_chat_proxies_and_preserves_tool_calls(mock_request, client):
    mock_request.return_value = MagicMock(
        status_code=200,
        json=lambda: {"message": {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "get_expenses"}}]}},
    )

    resp = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}], "tools": []})

    assert resp.status_code == 200
    assert resp.get_json()["message"]["tool_calls"][0]["function"]["name"] == "get_expenses"


@patch("ollama_client.requests.request")
def test_v1_chat_completions_proxies_to_openai_compatible_path(mock_request, client):
    mock_request.return_value = MagicMock(
        status_code=200,
        json=lambda: {"choices": [{"message": {"content": "Here is your income summary."}}]},
    )

    resp = client.post("/v1/chat/completions", json={"model": "qwen2.5:0.5b", "messages": []})

    assert resp.status_code == 200
    assert resp.get_json()["choices"][0]["message"]["content"] == "Here is your income summary."
    method, url = mock_request.call_args.args
    assert url.endswith("/chat/completions")


@patch("ollama_client.requests.request")
def test_v1_models_proxies_to_openai_compatible_path(mock_request, client):
    mock_request.return_value = MagicMock(
        status_code=200, json=lambda: {"data": [{"id": "qwen2.5:0.5b"}]}
    )

    resp = client.get("/v1/models")

    assert resp.status_code == 200
    assert resp.get_json()["data"][0]["id"] == "qwen2.5:0.5b"


@patch("ollama_client.requests.request")
def test_proxy_returns_502_when_upstream_unreachable(mock_request, client):
    import ollama_client
    mock_request.side_effect = ollama_client.requests.RequestException("connection refused")

    resp = client.post("/api/chat", json={"messages": []})

    assert resp.status_code == 502
    assert "error" in resp.get_json()
