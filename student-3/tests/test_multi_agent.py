"""Release 2 boundary tests: auth, owner identity, evidence, flags and failure handling."""
import importlib.util
from pathlib import Path

import pytest
import requests

SPEC = importlib.util.spec_from_file_location("income_multi_backend", Path(__file__).parents[1] / "backend/app.py")
backend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backend)


class Reply:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


@pytest.fixture
def boundary(monkeypatch):
    app = backend.create_app("http://db.test", "http://auth.test")
    app.config.update(TESTING=True, MULTI_AGENT_ENABLED=True, MULTI_AGENT_URL="http://multi.test")
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url == "http://auth.test/sessions/test-token":
            return Reply({"user": {"id": 31}})
        if url.startswith("http://db.test"):
            return Reply({"items": [{"id": 1, "user_id": 31}]})
        return Reply({"run_id": "run-1", "status": "awaiting_human_review"}, 201 if url.endswith("/runs") and method == "POST" else 200)

    monkeypatch.setattr(backend.requests, "request", request)
    return app, app.test_client(), calls


AUTH = {"Authorization": "Bearer test-token"}


@pytest.mark.parametrize("route", ["/api/multi-agent/run", "/api/multi-agent/runs/run-1/decision"])
def test_multi_agent_requires_authentication(boundary, route):
    _, client, calls = boundary
    assert client.post(route, json={"task": "Review income"}).status_code == 401
    assert calls == []


def test_run_uses_server_identity_and_database_evidence(boundary):
    _, client, calls = boundary
    response = client.post("/api/multi-agent/run", headers=AUTH,
                           json={"task": "Review income", "user_id": 999, "evidence": {"forged": True}})
    assert response.status_code == 201
    payload = next(c[2]["json"] for c in calls if c[1] == "http://multi.test/runs")
    assert payload["user_id"] == "31" and payload["module"] == "income"
    assert set(payload["evidence"]) == {"source", "income_sources", "pay_schedules"}
    assert all(c[2]["params"] == {"user_id": 31} for c in calls if c[1].startswith("http://db.test"))


def test_disabled_run_does_not_fetch_income_or_call_agents(boundary):
    app, client, calls = boundary
    app.config["MULTI_AGENT_ENABLED"] = False
    response = client.post("/api/multi-agent/run", headers=AUTH, json={"task": "Review"})
    assert response.status_code == 503 and response.json["code"] == "MULTI_AGENT_DISABLED"
    assert len(calls) == 1 and calls[0][1].startswith("http://auth.test")


@pytest.mark.parametrize("method,route", [("get", "/api/multi-agent/runs"), ("get", "/api/multi-agent/runs/run-1")])
def test_history_reads_cannot_select_another_owner(boundary, method, route):
    _, client, calls = boundary
    response = getattr(client, method)(route + "?user_id=999&module=budget", headers=AUTH)
    assert response.status_code == 200
    assert calls[-1][2]["params"] == {"module": "income", "user_id": "31"}


def test_human_decision_uses_authenticated_owner(boundary):
    _, client, calls = boundary
    response = client.post("/api/multi-agent/runs/run-1/decision", headers=AUTH,
                           json={"user_id": 999, "module": "budget", "decision": "correct", "feedback": "Check dates"})
    assert response.status_code == 200
    assert calls[-1][2]["json"] == {"module": "income", "user_id": "31", "decision": "correct", "feedback": "Check dates"}


def test_unavailable_server_returns_controlled_error(boundary, monkeypatch):
    _, client, calls = boundary
    original = backend.requests.request

    def request(method, url, **kwargs):
        if url.startswith("http://multi.test"):
            raise requests.ConnectionError("offline")
        return original(method, url, **kwargs)

    monkeypatch.setattr(backend.requests, "request", request)
    response = client.get("/api/multi-agent/runs", headers=AUTH)
    assert response.status_code == 502 and "unavailable" in response.json["error"]
