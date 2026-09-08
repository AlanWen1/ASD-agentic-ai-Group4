import os
import sys
import importlib.util
from unittest.mock import MagicMock, patch

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

BACKEND_PATH = os.path.join(BACKEND_DIR, "app.py")

spec = importlib.util.spec_from_file_location(
    "student5_backend_app",
    BACKEND_PATH
)

backend_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_app)


def make_client():
    backend_app.app.config["TESTING"] = True
    return backend_app.app.test_client()


def test_goals_without_token_rejected():
    client = make_client()

    response = client.get("/goals")

    assert response.status_code == 401


@patch.object(backend_app.requests, "get")
def test_goals_with_invalid_token_rejected(mock_get):
    client = make_client()

    mock_get.return_value = MagicMock(
        status_code=404,
        json=lambda: {"error": "Session not found"},
    )

    response = client.get(
        "/goals",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


@patch.object(backend_app.requests, "get")
def test_authenticated_user_only_sees_own_goals(mock_get):
    client = make_client()

    def side_effect(url, **kwargs):
        if "/sessions/" in url:
            return MagicMock(
                status_code=200,
                json=lambda: {
                    "user": {
                        "id": 42,
                        "username": "test-user",
                    }
                },
            )

        return MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "goal_id": 1,
                    "user_id": 42,
                    "goal_name": "My Goal",
                    "target_amount": 5000,
                    "current_amount": 1000,
                    "target_date": "2027-12-31",
                },
                {
                    "goal_id": 2,
                    "user_id": 99,
                    "goal_name": "Other User Goal",
                    "target_amount": 10000,
                    "current_amount": 2000,
                    "target_date": "2028-12-31",
                },
            ],
        )

    mock_get.side_effect = side_effect

    response = client.get(
        "/goals",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200

    goals = response.get_json()

    assert len(goals) == 1
    assert goals[0]["user_id"] == 42
    assert goals[0]["goal_name"] == "My Goal"