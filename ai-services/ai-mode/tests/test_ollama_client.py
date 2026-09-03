import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ollama_client


@patch("ollama_client.requests.post")
def test_generate_returns_stripped_response_text(mock_post):
    mock_post.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: {"response": "  Groceries  "},
    )

    result = ollama_client.generate("classify this expense")

    assert result == "Groceries"
    called_url = mock_post.call_args.args[0]
    assert called_url == f"{ollama_client.DEFAULT_URL}/api/generate"
    assert mock_post.call_args.kwargs["json"]["model"] == ollama_client.DEFAULT_MODEL
    assert mock_post.call_args.kwargs["json"]["stream"] is False


@patch("ollama_client.requests.post")
def test_generate_raises_ollama_error_on_request_failure(mock_post):
    mock_post.side_effect = ollama_client.requests.RequestException("boom")

    with pytest.raises(ollama_client.OllamaError):
        ollama_client.generate("classify this expense")


@patch("ollama_client.requests.post")
def test_chat_returns_message_dict_and_forwards_tools(mock_post):
    mock_post.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: {"message": {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "get_expenses"}}]}},
    )
    tools = [{"type": "function", "function": {"name": "get_expenses"}}]

    result = ollama_client.chat([{"role": "user", "content": "hi"}], tools=tools)

    assert result["tool_calls"][0]["function"]["name"] == "get_expenses"
    assert mock_post.call_args.kwargs["json"]["tools"] == tools


@patch("ollama_client.requests.post")
def test_chat_raises_ollama_error_on_request_failure(mock_post):
    mock_post.side_effect = ollama_client.requests.RequestException("boom")

    with pytest.raises(ollama_client.OllamaError):
        ollama_client.chat([{"role": "user", "content": "hi"}])


@patch("ollama_client.requests.get")
def test_health_check_reports_ok_when_reachable(mock_get):
    mock_get.return_value = MagicMock(ok=True)

    result = ollama_client.health_check(model="qwen2.5:0.5b", base_url="http://ollama:11434")

    assert result == {
        "ollama": True,
        "ollama_model": "qwen2.5:0.5b",
        "ollama_url": "http://ollama:11434",
    }


@patch("ollama_client.requests.get")
def test_health_check_reports_not_ok_without_raising(mock_get):
    mock_get.side_effect = ollama_client.requests.RequestException("connection refused")

    result = ollama_client.health_check()

    assert result["ollama"] is False
