"""Post-commit endpoint tests for Income & Pay Schedule Manager."""
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import app as income_backend  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def make_client(monkeypatch):
    app = income_backend.create_app(database_url="http://test-database", auth_url="http://test-auth")
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url == "http://test-auth/sessions/test-token":
            return FakeResponse({"user": {"id": 31}})
        if url == "http://test-database/api/income-sources":
            return FakeResponse({"items": [{"id": 3, "name": "Salary", "amount": 1200}]})
        if url == "http://test-database/api/pay-schedules":
            return FakeResponse({"items": [{"id": 8, "expected_amount": "1200.00"}]})
        raise AssertionError(f"Unexpected downstream request: {method} {url}")

    monkeypatch.setattr(income_backend.requests, "request", fake_request)
    return app.test_client(), calls


def test_income_sources_endpoint_is_user_scoped(monkeypatch):
    client, calls = make_client(monkeypatch)
    response = client.get("/api/income-sources", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.get_json()["items"][0]["name"] == "Salary"
    assert any(
        call[1] == "http://test-database/api/income-sources"
        and call[2].get("params") == {"user_id": 31}
        for call in calls
    )


def test_pay_schedules_endpoint_is_user_scoped(monkeypatch):
    client, calls = make_client(monkeypatch)
    response = client.get("/api/pay-schedules", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.get_json()["items"][0]["id"] == 8
    assert any(
        call[1] == "http://test-database/api/pay-schedules"
        and call[2].get("params") == {"user_id": 31}
        for call in calls
    )