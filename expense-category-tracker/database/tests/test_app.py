import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp()
    os.environ["DATABASE_PATH"] = db_path

    import database
    importlib.reload(database)
    import app as app_module
    importlib.reload(app_module)

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client

    os.close(db_fd)
    os.unlink(db_path)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_create_and_list_category(client):
    resp = client.post("/categories", json={"name": "Groceries", "type": "Essential"})
    assert resp.status_code == 201
    resp = client.get("/categories")
    assert resp.status_code == 200
    assert any(c["name"] == "Groceries" for c in resp.get_json())


def test_duplicate_category_rejected(client):
    client.post("/categories", json={"name": "Dining"})
    resp = client.post("/categories", json={"name": "Dining"})
    assert resp.status_code == 409


def test_create_and_get_expense(client):
    cat = client.post("/categories", json={"name": "Transport"}).get_json()
    resp = client.post(
        "/expenses",
        json={"amount": 12.5, "description": "Bus fare", "category_id": cat["id"], "date": "2026-01-01"},
    )
    assert resp.status_code == 201
    expense_id = resp.get_json()["id"]
    resp = client.get(f"/expenses/{expense_id}")
    assert resp.status_code == 200
    assert resp.get_json()["description"] == "Bus fare"


def test_update_and_delete_expense(client):
    resp = client.post("/expenses", json={"amount": 5, "description": "Snack", "date": "2026-01-02"})
    expense_id = resp.get_json()["id"]

    resp = client.put(f"/expenses/{expense_id}", json={"amount": 7.5})
    assert resp.status_code == 200
    assert resp.get_json()["amount"] == 7.5

    resp = client.delete(f"/expenses/{expense_id}")
    assert resp.status_code == 204
    assert client.get(f"/expenses/{expense_id}").status_code == 404
