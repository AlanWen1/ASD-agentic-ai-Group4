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


def test_categories_and_expenses_require_user_id(client):
    assert client.get("/categories").status_code == 400
    assert client.post("/categories", json={"name": "Groceries"}).status_code == 400
    assert client.get("/expenses").status_code == 400
    assert client.post("/expenses", json={"amount": 1, "description": "x", "date": "2026-01-01"}).status_code == 400


def test_create_and_list_category(client):
    resp = client.post("/categories?user_id=1", json={"name": "Groceries", "type": "Essential"})
    assert resp.status_code == 201
    resp = client.get("/categories?user_id=1")
    assert resp.status_code == 200
    assert any(c["name"] == "Groceries" for c in resp.get_json())


def test_duplicate_category_rejected_for_same_user(client):
    client.post("/categories?user_id=1", json={"name": "Dining"})
    resp = client.post("/categories?user_id=1", json={"name": "Dining"})
    assert resp.status_code == 409


def test_same_category_name_allowed_for_different_users(client):
    resp1 = client.post("/categories?user_id=1", json={"name": "Dining"})
    resp2 = client.post("/categories?user_id=2", json={"name": "Dining"})
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.get_json()["id"] != resp2.get_json()["id"]


def test_create_and_get_expense(client):
    cat = client.post("/categories?user_id=1", json={"name": "Transport"}).get_json()
    resp = client.post(
        "/expenses?user_id=1",
        json={"amount": 12.5, "description": "Bus fare", "category_id": cat["id"], "date": "2026-01-01"},
    )
    assert resp.status_code == 201
    expense_id = resp.get_json()["id"]
    resp = client.get(f"/expenses/{expense_id}?user_id=1")
    assert resp.status_code == 200
    assert resp.get_json()["description"] == "Bus fare"


def test_update_and_delete_expense(client):
    resp = client.post("/expenses?user_id=1", json={"amount": 5, "description": "Snack", "date": "2026-01-02"})
    expense_id = resp.get_json()["id"]

    resp = client.put(f"/expenses/{expense_id}?user_id=1", json={"amount": 7.5})
    assert resp.status_code == 200
    assert resp.get_json()["amount"] == 7.5

    resp = client.delete(f"/expenses/{expense_id}?user_id=1")
    assert resp.status_code == 204
    assert client.get(f"/expenses/{expense_id}?user_id=1").status_code == 404


def test_users_cannot_see_each_others_expenses(client):
    cat1 = client.post("/categories?user_id=1", json={"name": "Groceries"}).get_json()
    exp1 = client.post(
        "/expenses?user_id=1",
        json={"amount": 100, "description": "User 1's rent", "category_id": cat1["id"], "date": "2026-01-01"},
    ).get_json()

    client.post("/categories?user_id=2", json={"name": "Groceries"})
    client.post(
        "/expenses?user_id=2",
        json={"amount": 5, "description": "User 2's coffee", "date": "2026-01-01"},
    )

    # User 2's expense list must not contain user 1's expense.
    resp = client.get("/expenses?user_id=2")
    descriptions = [e["description"] for e in resp.get_json()]
    assert "User 1's rent" not in descriptions

    # User 2 cannot fetch, update, or delete user 1's expense by id.
    assert client.get(f"/expenses/{exp1['id']}?user_id=2").status_code == 404
    assert client.put(f"/expenses/{exp1['id']}?user_id=2", json={"amount": 1}).status_code == 404
    assert client.delete(f"/expenses/{exp1['id']}?user_id=2").status_code == 404

    # User 1's data is untouched.
    assert client.get(f"/expenses/{exp1['id']}?user_id=1").status_code == 200


def test_users_cannot_see_or_delete_each_others_categories(client):
    cat1 = client.post("/categories?user_id=1", json={"name": "Health"}).get_json()
    client.post("/categories?user_id=2", json={"name": "Travel"})

    resp = client.get("/categories?user_id=2")
    names = [c["name"] for c in resp.get_json()]
    assert "Health" not in names

    # User 2 cannot delete or edit user 1's category.
    assert client.delete(f"/categories/{cat1['id']}?user_id=2").status_code == 204  # no-op, nothing owned deleted
    assert client.get(f"/categories?user_id=1").status_code == 200
    assert any(c["id"] == cat1["id"] for c in client.get("/categories?user_id=1").get_json())

    assert client.put(f"/categories/{cat1['id']}?user_id=2", json={"name": "Hacked"}).status_code == 404


def test_expense_rejects_another_users_category_id(client):
    cat2 = client.post("/categories?user_id=2", json={"name": "Shopping"}).get_json()
    resp = client.post(
        "/expenses?user_id=1",
        json={"amount": 1, "description": "x", "category_id": cat2["id"], "date": "2026-01-01"},
    )
    assert resp.status_code == 400
