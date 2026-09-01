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


def test_suggest_category_requires_auth(client):
    resp = client.post("/api/expenses/suggest-category", json={"description": "coffee"})
    assert resp.status_code == 401
