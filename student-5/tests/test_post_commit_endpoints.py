"""Post-commit endpoint tests for Savings Goal Manager."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import app as backend  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


GOAL = {
    "goal_id": 9,
    "user_id": 52,
    "goal_name": "Emergency fund",
    "target_amount": 2000,
    "current_amount": 500,
    "target_date": "2027-12-31",
}


def test_goal_collection_returns_only_users_goals(monkeypatch):
    monkeypatch.setattr(backend, "current_user", lambda: ({"id": 52}, None))
    monkeypatch.setattr(
        backend.requests,
        "get",
        lambda url, **kwargs: FakeResponse([GOAL, {**GOAL, "goal_id": 10, "user_id": 88}]),
    )

    response = backend.app.test_client().get("/goals")

    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["user_id"] == 52
    assert "progress_percentage" in data[0]


def test_goal_detail_endpoint_includes_calculated_fields(monkeypatch):
    monkeypatch.setattr(backend, "current_user", lambda: ({"id": 52}, None))
    monkeypatch.setattr(
        backend.requests,
        "get",
        lambda url, **kwargs: FakeResponse(GOAL) if url.endswith("/goals/9") else FakeResponse([]),
    )

    response = backend.app.test_client().get("/goals/9")

    assert response.status_code == 200
    data = response.get_json()
    assert data["goal_id"] == 9
    assert data["remaining_amount"] == 1500
    assert "required_monthly_contribution" in data