import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200


def test_get_categories(client):
    response = client.get("/api/categories")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_get_expenses(client):
    response = client.get("/api/expenses")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_create_and_delete_expense(client):
    create_resp = client.post(
        "/api/expenses",
        json={
            "amount": 10.5,
            "description": "Test coffee",
            "merchant": "Test Cafe",
            "category_id": None,
            "date": "2026-08-27",
        },
    )
    assert create_resp.status_code == 201
    new_id = create_resp.get_json()["id"]

    delete_resp = client.delete(f"/api/expenses/{new_id}")
    assert delete_resp.status_code == 204


def test_create_and_delete_category(client):
    create_resp = client.post(
        "/api/categories",
        json={"name": "TestCategory", "type": "Discretionary"},
    )
    assert create_resp.status_code == 201
    new_id = create_resp.get_json()["id"]

    delete_resp = client.delete(f"/api/categories/{new_id}")
    assert delete_resp.status_code == 204
