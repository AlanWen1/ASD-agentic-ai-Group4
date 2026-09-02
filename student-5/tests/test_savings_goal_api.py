import pytest
import requests
import time

BASE_URL = "http://localhost:5005"


@pytest.fixture(scope="module")
def created_goal():
    payload = {
        "user_id": 99,
        "goal_name": "Test Savings Goal",
        "target_amount": 3000,
        "current_amount": 500,
        "target_date": "2027-12-31"
    }

    response = requests.post(f"{BASE_URL}/goals", json=payload)

    assert response.status_code == 201

    return response.json()["goal_id"]


def test_get_all_goals():
    response = requests.get(f"{BASE_URL}/goals")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_goal():
    payload = {
        "user_id": 99,
        "goal_name": "Laptop Test Goal",
        "target_amount": 2500,
        "current_amount": 500,
        "target_date": "2027-06-30"
    }

    response = requests.post(f"{BASE_URL}/goals", json=payload)

    assert response.status_code == 201
    assert "goal_id" in response.json()


def test_get_single_goal(created_goal):
    response = requests.get(f"{BASE_URL}/goals/{created_goal}")

    assert response.status_code == 200

    data = response.json()

    assert data["goal_id"] == created_goal
    assert data["goal_name"] == "Test Savings Goal"
    assert "progress_percentage" in data
    assert "remaining_amount" in data
    assert "required_monthly_contribution" in data


def test_update_goal(created_goal):
    payload = {
        "user_id": 99,
        "goal_name": "Updated Test Goal",
        "target_amount": 4000,
        "current_amount": 1000,
        "target_date": "2028-01-01"
    }

    response = requests.put(
        f"{BASE_URL}/goals/{created_goal}",
        json=payload
    )

    assert response.status_code == 200

    response = requests.get(f"{BASE_URL}/goals/{created_goal}")
    data = response.json()

    assert data["goal_name"] == "Updated Test Goal"
    assert data["target_amount"] == 4000
    assert data["current_amount"] == 1000


def test_goal_not_found():
    response = requests.get(f"{BASE_URL}/goals/999999")

    assert response.status_code == 404


def test_ai_explanation(created_goal):
    response = requests.get(
        f"{BASE_URL}/goals/{created_goal}/explanation"
    )

    assert response.status_code == 200

    data = response.json()

    assert "explanation" in data
    assert data["goal_id"] == created_goal


def test_delete_goal(created_goal):
    response = requests.delete(f"{BASE_URL}/goals/{created_goal}")

    assert response.status_code == 200

    response = requests.get(f"{BASE_URL}/goals/{created_goal}")

    assert response.status_code == 404


def test_get_goals_response_time():
    start_time = time.perf_counter()

    response = requests.get(f"{BASE_URL}/goals")

    end_time = time.perf_counter()
    response_time = end_time - start_time

    print(f"GET /goals response time: {response_time:.3f} seconds")

    assert response.status_code == 200
    assert response_time < 3.0