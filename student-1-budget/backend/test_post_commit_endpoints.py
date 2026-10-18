"""Post-commit endpoint smoke tests for the Budget Manager backend."""
from types import SimpleNamespace

import app as backend


def test_list_budgets_for_authenticated_user(monkeypatch):
    monkeypatch.setattr(backend, "current_user", lambda: ({"id": 17}, None))
    calls = []

    def fake_db_get(path, params=None):
        calls.append((path, params))
        return SimpleNamespace(json=lambda: [{"budget_id": 42, "month": 10}], status_code=200)

    monkeypatch.setattr(backend, "db_get", fake_db_get)
    response = backend.app.test_client().get("/api/budgets")

    assert response.status_code == 200
    assert response.get_json() == [{"budget_id": 42, "month": 10}]
    assert calls == [("/api/budgets", {"user_id": 17})]


def test_get_budget_for_authenticated_user(monkeypatch):
    monkeypatch.setattr(backend, "current_user", lambda: ({"id": 17}, None))
    calls = []

    def fake_db_get(path, params=None):
        calls.append((path, params))
        return SimpleNamespace(json=lambda: {"budget_id": 42, "user_id": 17}, status_code=200)

    monkeypatch.setattr(backend, "db_get", fake_db_get)
    response = backend.app.test_client().get("/api/budgets/42")

    assert response.status_code == 200
    assert response.get_json()["budget_id"] == 42
    assert calls == [("/api/budgets/42", {"user_id": 17})]