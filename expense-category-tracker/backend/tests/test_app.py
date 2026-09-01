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


@patch("app.requests.request")
def test_list_categories_forwards_to_database(mock_request, client):
    mock_request.return_value = MagicMock(
        ok=True, status_code=200, json=lambda: [{"id": 1, "name": "Groceries"}]
    )
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    assert resp.get_json()[0]["name"] == "Groceries"
    mock_request.assert_called_once()
    assert mock_request.call_args[0][0] == "GET"
    assert mock_request.call_args[0][1].endswith("/categories")


@patch("app.requests.request")
def test_create_expense_forwards_body(mock_request, client):
    mock_request.return_value = MagicMock(
        ok=True, status_code=201, json=lambda: {"id": 5, "amount": 12.5}
    )
    resp = client.post("/api/expenses", json={"amount": 12.5, "description": "Bus", "date": "2026-01-01"})
    assert resp.status_code == 201
    assert resp.get_json()["id"] == 5


@patch("app.requests.request")
def test_database_unavailable_returns_503(mock_request, client):
    import requests
    mock_request.side_effect = requests.exceptions.ConnectionError()
    resp = client.get("/api/expenses")
    assert resp.status_code == 503


@patch("app.requests.post")
def test_suggest_category_matches_allowed_list(mock_post, client):
    mock_post.return_value = MagicMock(
        ok=True, json=lambda: {"response": "Groceries"}, raise_for_status=lambda: None
    )
    resp = client.post(
        "/api/expenses/suggest-category",
        json={"description": "Weekly shop", "merchant": "Woolworths"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["category"] == "Groceries"


@patch("app.requests.post")
def test_suggest_category_ai_unavailable_falls_back_to_other(mock_post, client):
    import requests
    mock_post.side_effect = requests.exceptions.ConnectionError()
    resp = client.post(
        "/api/expenses/suggest-category",
        json={"description": "Something", "merchant": ""},
    )
    assert resp.status_code == 200
    assert resp.get_json()["category"] == "Other"
