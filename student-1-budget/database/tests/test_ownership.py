"""Regression for cross-user budget/category reads and mutations."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("budget_database_ownership", Path(__file__).parents[1] / "app.py")
database = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(database)


@pytest.fixture
def records(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "budget.db"))
    database.init_db()
    client = database.app.test_client()
    budget = client.post("/api/budgets", json={"user_id": 31, "month": 1, "year": 2099}).get_json()["budget_id"]
    category = client.post(f"/api/budgets/{budget}/categories", json={"user_id": 31,
        "category_name": "Private", "allocated_amount": 25}).get_json()["category_id"]
    return client, budget, category


@pytest.mark.parametrize("method", ["get", "put", "delete"])
@pytest.mark.parametrize("kind", ["budget", "category"])
def test_other_owner_cannot_read_or_mutate(records, method, kind):
    client, budget, category = records
    route = f"/api/budgets/{budget}" if kind == "budget" else f"/api/categories/{category}"
    assert getattr(client, method)(route + "?user_id=32", json={"user_id":32}).status_code == 404
    assert client.get(route + "?user_id=31").status_code == 200


def test_other_owner_cannot_read_or_add_nested_categories(records):
    client, budget, _ = records
    route = f"/api/budgets/{budget}/categories"
    assert client.get(route + "?user_id=32").status_code == 404
    assert client.post(route, json={"user_id":32, "category_name":"Intruder", "allocated_amount":1}).status_code == 404


def test_database_refuses_unscoped_budget_lists(records):
    client, _, _ = records
    assert client.get("/api/budgets").status_code == 400
    assert client.get("/api/health").status_code == 200
