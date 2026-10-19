"""Post-commit endpoint smoke tests for Expense & Category Manager."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as backend  # noqa: E402


def test_categories_endpoint_forwards_user(monkeypatch):
    monkeypatch.setattr(backend, "current_user", lambda: ({"id": 23}, None))
    calls = []

    def fake_forward(method, path, body=None, params=None, user_id=None):
        calls.append((method, path, body, params, user_id))
        return backend.jsonify([{"id": 1, "name": "Groceries"}]), 200

    monkeypatch.setattr(backend, "forward", fake_forward)
    response = backend.app.test_client().get("/api/categories")

    assert response.status_code == 200
    assert response.get_json() == [{"id": 1, "name": "Groceries"}]
    assert calls == [("GET", "/categories", None, None, 23)]


def test_expenses_endpoint_forwards_category_filter(monkeypatch):
    monkeypatch.setattr(backend, "current_user", lambda: ({"id": 23}, None))
    calls = []

    def fake_forward(method, path, body=None, params=None, user_id=None):
        calls.append((method, path, body, params, user_id))
        return backend.jsonify([{"id": 7, "category_id": 9, "amount": 12.5}]), 200

    monkeypatch.setattr(backend, "forward", fake_forward)
    response = backend.app.test_client().get("/api/expenses?category_id=9")

    assert response.status_code == 200
    assert response.get_json()[0]["category_id"] == 9
    assert calls == [("GET", "/expenses", None, {"category_id": "9"}, 23)]