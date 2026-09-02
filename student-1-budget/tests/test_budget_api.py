import pytest
import requests

BASE_URL = "http://localhost:5001/api"
HEADERS = {"X-User-Id": "pytest_user"}


@pytest.fixture(scope="module")
def created_budget():
    payload = {"month": 6, "year": 2026, "status": "active"}
    resp = requests.post(f"{BASE_URL}/budgets", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    return resp.json()


def test_health_check():
    resp = requests.get(f"{BASE_URL}/health")
    assert resp.status_code == 200


def test_create_budget():
    payload = {"month": 3, "year": 2026, "status": "active"}
    resp = requests.post(f"{BASE_URL}/budgets", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["month"] == 3
    assert data["year"] == 2026


def test_get_all_budgets():
    resp = requests.get(f"{BASE_URL}/budgets", headers=HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_single_budget(created_budget):
    budget_id = created_budget["budget_id"]
    resp = requests.get(f"{BASE_URL}/budgets/{budget_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["budget_id"] == budget_id


def test_update_budget(created_budget):
    budget_id = created_budget["budget_id"]
    payload = {"status": "archived"}
    resp = requests.put(f"{BASE_URL}/budgets/{budget_id}", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


def test_create_category(created_budget):
    budget_id = created_budget["budget_id"]
    payload = {"category_name": "Test Category", "allocated_amount": 100.0}
    resp = requests.post(f"{BASE_URL}/budgets/{budget_id}/categories", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    assert resp.json()["category_name"] == "Test Category"


def test_get_categories(created_budget):
    budget_id = created_budget["budget_id"]
    resp = requests.get(f"{BASE_URL}/budgets/{budget_id}/categories", headers=HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_cross_user_isolation(created_budget):
    other_headers = {"X-User-Id": "different_user"}
    resp = requests.get(f"{BASE_URL}/budgets", headers=other_headers)
    assert resp.status_code == 200
    budget_ids = [b["budget_id"] for b in resp.json()]
    assert created_budget["budget_id"] not in budget_ids


def test_delete_budget(created_budget):
    budget_id = created_budget["budget_id"]
    resp = requests.delete(f"{BASE_URL}/budgets/{budget_id}", headers=HEADERS)
    assert resp.status_code in (200, 204)


def test_agent_chat_reachable():
    payload = {"message": "list my budgets"}
    resp = requests.post(f"{BASE_URL}/agent/chat", json=payload, headers=HEADERS)
    assert resp.status_code in (200, 502)