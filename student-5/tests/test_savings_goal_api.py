import pytest
import requests
import time
import uuid

BASE_URL = "http://localhost:5005"
AUTH_URL = "http://localhost:5000"


@pytest.fixture(scope="module")
def auth_headers():
    unique_id = uuid.uuid4().hex[:8]

    username = f"testuser_{unique_id}"
    email = f"{username}@example.com"
    password = "TestPassword123!"

    register_response = requests.post(
        f"{AUTH_URL}/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password
        }
    )

    assert register_response.status_code == 201

    login_response = requests.post(
        f"{AUTH_URL}/auth/login",
        json={
            "identifier": username,
            "password": password
        }
    )

    assert login_response.status_code == 200

    token = login_response.json()["token"]

    return {
        "Authorization": f"Bearer {token}"
    }


@pytest.fixture(scope="module")
def created_goal(auth_headers):
    payload = {
        "goal_name": "Test Savings Goal",
        "target_amount": 3000,
        "current_amount": 500,
        "target_date": "2027-12-31"
    }

    response = requests.post(
        f"{BASE_URL}/goals",
        json=payload,
        headers=auth_headers
    )

    assert response.status_code == 201

    return response.json()["goal_id"]


def test_get_all_goals(auth_headers):
    response = requests.get(
        f"{BASE_URL}/goals",
        headers=auth_headers
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_goal(auth_headers):
    payload = {
        "goal_name": "Laptop Test Goal",
        "target_amount": 2500,
        "current_amount": 500,
        "target_date": "2027-06-30"
    }

    response = requests.post(
        f"{BASE_URL}/goals",
        json=payload,
        headers=auth_headers
    )

    assert response.status_code == 201
    assert "goal_id" in response.json()


def test_get_single_goal(created_goal, auth_headers):
    response = requests.get(
        f"{BASE_URL}/goals/{created_goal}",
        headers=auth_headers
    )

    assert response.status_code == 200

    data = response.json()

    assert data["goal_id"] == created_goal
    assert data["goal_name"] == "Test Savings Goal"
    assert "progress_percentage" in data
    assert "remaining_amount" in data
    assert "required_monthly_contribution" in data


def test_update_goal(created_goal, auth_headers):
    payload = {
        "goal_name": "Updated Test Goal",
        "target_amount": 4000,
        "current_amount": 1000,
        "target_date": "2028-01-01"
    }

    response = requests.put(
        f"{BASE_URL}/goals/{created_goal}",
        json=payload,
        headers=auth_headers
    )

    assert response.status_code == 200

    response = requests.get(
        f"{BASE_URL}/goals/{created_goal}",
        headers=auth_headers
    )

    data = response.json()

    assert data["goal_name"] == "Updated Test Goal"
    assert data["target_amount"] == 4000
    assert data["current_amount"] == 1000


def test_goal_not_found(auth_headers):
    response = requests.get(
        f"{BASE_URL}/goals/999999",
        headers=auth_headers
    )

    assert response.status_code == 404


def test_ai_explanation(created_goal, auth_headers):
    response = requests.get(
        f"{BASE_URL}/goals/{created_goal}/explanation",
        headers=auth_headers
    )

    assert response.status_code == 200

    data = response.json()

    assert "explanation" in data
    assert data["goal_id"] == created_goal


def test_delete_goal(created_goal, auth_headers):
    response = requests.delete(
        f"{BASE_URL}/goals/{created_goal}",
        headers=auth_headers
    )

    assert response.status_code == 200

    response = requests.get(
        f"{BASE_URL}/goals/{created_goal}",
        headers=auth_headers
    )

    assert response.status_code == 404


def test_get_goals_response_time(auth_headers):
    start_time = time.perf_counter()

    response = requests.get(
        f"{BASE_URL}/goals",
        headers=auth_headers
    )

    end_time = time.perf_counter()
    response_time = end_time - start_time

    print(
        f"GET /goals response time: "
        f"{response_time:.3f} seconds"
    )

    assert response.status_code == 200
    assert response_time < 3.0