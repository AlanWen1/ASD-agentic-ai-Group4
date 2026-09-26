import pytest
import requests

BASE_URL = "http://localhost:5001/api"
AUTH_URL = "http://localhost:6000"

# ---------------------------------------------------------------------------
# Auth fixture — obtains a real Bearer token from finance-database.
# Uses a well-known CI test user; creates it if it doesn't already exist.
# ---------------------------------------------------------------------------

TEST_USER = {
    "username": "pytest_budget_user",
    "email": "pytest_budget@test.com",
    "password": "pytest_password_123",
}


def _get_token(user):
    login_resp = requests.post(
        f"{AUTH_URL}/auth/login",
        json={"identifier": user["username"], "password": user["password"]},
    )
    if login_resp.status_code == 200:
        token = login_resp.json().get("token")
        assert token, f"No token in login response: {login_resp.json()}"
        return token

    reg_resp = requests.post(f"{AUTH_URL}/users", json=user)
    assert reg_resp.status_code in (201, 409), (
        f"Could not create test user: {reg_resp.status_code} {reg_resp.text}"
    )

    login_resp = requests.post(
        f"{AUTH_URL}/auth/login",
        json={"identifier": user["username"], "password": user["password"]},
    )
    assert login_resp.status_code == 200, (
        f"Login failed after creation: {login_resp.status_code} {login_resp.text}"
    )
    token = login_resp.json().get("token")
    assert token
    return token


@pytest.fixture(scope="module")
def auth_headers():
    """Return Authorization header dict for the CI test user."""
    token = _get_token(TEST_USER)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def other_auth_headers():
    other_user = {
        "username": "pytest_budget_other",
        "email": "pytest_budget_other@test.com",
        "password": "pytest_password_456",
    }
    token = _get_token(other_user)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def created_budget(auth_headers):
    payload = {"month": 6, "year": 2026, "status": "active"}
    resp = requests.post(f"{BASE_URL}/budgets", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health_check():
    resp = requests.get(f"{BASE_URL}/health")
    assert resp.status_code == 200


def test_create_budget(auth_headers):
    payload = {"month": 3, "year": 2026, "status": "active"}
    resp = requests.post(f"{BASE_URL}/budgets", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["month"] == 3
    assert data["year"] == 2026


def test_get_all_budgets(auth_headers):
    resp = requests.get(f"{BASE_URL}/budgets", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_single_budget(auth_headers, created_budget):
    budget_id = created_budget["budget_id"]
    resp = requests.get(f"{BASE_URL}/budgets/{budget_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["budget_id"] == budget_id


def test_update_budget(auth_headers, created_budget):
    budget_id = created_budget["budget_id"]
    payload = {"status": "archived"}
    resp = requests.put(f"{BASE_URL}/budgets/{budget_id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


def test_create_category(auth_headers, created_budget):
    budget_id = created_budget["budget_id"]
    payload = {"category_name": "Test Category", "allocated_amount": 100.0}
    resp = requests.post(
        f"{BASE_URL}/budgets/{budget_id}/categories",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["category_name"] == "Test Category"


def test_get_categories(auth_headers, created_budget):
    budget_id = created_budget["budget_id"]
    resp = requests.get(
        f"{BASE_URL}/budgets/{budget_id}/categories", headers=auth_headers
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_cross_user_isolation(auth_headers, other_auth_headers, created_budget):
    """Budgets created by the primary test user must not appear for a different user."""
    resp = requests.get(f"{BASE_URL}/budgets", headers=other_auth_headers)
    assert resp.status_code == 200
    budget_ids = [b["budget_id"] for b in resp.json()]
    assert created_budget["budget_id"] not in budget_ids


def test_delete_budget(auth_headers, created_budget):
    budget_id = created_budget["budget_id"]
    resp = requests.delete(f"{BASE_URL}/budgets/{budget_id}", headers=auth_headers)
    assert resp.status_code in (200, 204)


def test_agent_chat_reachable(auth_headers):
    payload = {"message": "list my budgets"}
    resp = requests.post(f"{BASE_URL}/agent/chat", json=payload, headers=auth_headers)
    assert resp.status_code in (200, 502)