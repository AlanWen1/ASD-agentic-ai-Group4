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


def test_no_session_shows_gate(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Sign in required" in resp.data


def test_token_in_url_is_captured_and_redirects(client):
    resp = client.get("/?token=abc123")
    assert resp.status_code in (301, 302)
    assert "token" not in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess["finance_token"] == "abc123"


@patch("app.requests.get")
def test_signed_in_loads_index(mock_get, client):
    with client.session_transaction() as sess:
        sess["finance_token"] = "abc123"
    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: []),
        MagicMock(status_code=200, json=lambda: []),
    ]
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Sign in required" not in resp.data


@patch("app.requests.get")
def test_expired_session_clears_and_shows_gate(mock_get, client):
    with client.session_transaction() as sess:
        sess["finance_token"] = "expiredtoken"
    mock_get.side_effect = [
        MagicMock(status_code=401),
        MagicMock(status_code=401),
    ]
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Sign in required" in resp.data
    with client.session_transaction() as sess:
        assert "finance_token" not in sess
