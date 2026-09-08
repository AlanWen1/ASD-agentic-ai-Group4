from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from urllib.parse import urlparse


BACKEND_DIR = Path(__file__).parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
SPEC = importlib.util.spec_from_file_location("student3_backend_app", BACKEND_DIR / "app.py")
backend_module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(backend_module)
import ai_service as ai_service_module


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


SOURCES = {
    "items": [
        {"id": 1, "source_name": "Job", "standard_amount": 1000, "payment_frequency": "fortnightly", "active": 1},
        {"id": 2, "source_name": "Freelance", "standard_amount": 500, "payment_frequency": "monthly", "active": 1},
    ],
    "count": 2,
}
SCHEDULES = {
    "items": [
        {"id": 1, "income_source_id": 1, "source_name": "Job", "expected_pay_date": "2026-08-14", "expected_amount": 1000, "received_date": "2026-08-14", "actual_amount": 1020, "status": "received"},
        {"id": 2, "income_source_id": 1, "source_name": "Job", "expected_pay_date": "2026-08-28", "expected_amount": 1000, "received_date": None, "actual_amount": None, "status": "scheduled"},
        {"id": 3, "income_source_id": 2, "source_name": "Freelance", "expected_pay_date": "2026-08-20", "expected_amount": 500, "received_date": None, "actual_amount": None, "status": "late"},
    ],
    "count": 3,
}
AUTH_HEADERS = {"Authorization": "Bearer valid-token"}


def fake_database_request(method, url, **kwargs):
    path = urlparse(url).path
    if path == "/sessions/valid-token" and method == "GET":
        return FakeResponse({"user": {"id": 1, "username": "test-user"}})
    if path.startswith("/sessions/") and method == "GET":
        return FakeResponse({"error": "Session not found"}, 404)
    if path == "/api/income-sources" and method == "GET":
        return FakeResponse(SOURCES)
    if path == "/api/pay-schedules" and method == "GET":
        return FakeResponse(SCHEDULES)
    if path == "/api/income-sources/1" and method == "GET":
        return FakeResponse(SOURCES["items"][0])
    if path == "/api/pay-schedules" and method == "POST":
        return FakeResponse({"id": 99, **kwargs["json"]}, 201)
    raise AssertionError(f"Unexpected database request: {method} {path}")


def make_client(monkeypatch):
    monkeypatch.setattr(backend_module.requests, "request", fake_database_request)
    app = backend_module.create_app("http://database.test", "http://auth.test")
    app.config.update(TESTING=True)
    return app.test_client()


def test_dashboard_calculates_money_without_ai(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/dashboard?month=2026-08", headers=AUTH_HEADERS)
    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["expected_total"] == 2500.0
    assert summary["received_total"] == 1020.0
    assert summary["outstanding_total"] == 1500.0
    assert summary["variance"] == 20.0
    assert summary["late_count"] == 1


def test_ai_chat_runs_user_scoped_agent_tools(monkeypatch):
    client = make_client(monkeypatch)
    captured = {}

    def fake_agent(question, selected_month, execute_tool, history=None):
        captured.update(
            {
                "question": question,
                "month": selected_month,
                "summary": execute_tool("get_month_summary", {}),
                "outstanding": execute_tool("get_outstanding_payments", {}),
                "history": history,
            }
        )
        return {
            "answer": "Two payments totalling AUD 1500.00 are outstanding.",
            "trace": [
                {"step": 1, "phase": "Plan", "detail": "Selected an income tool."},
                {"step": 1, "phase": "Act", "detail": "Executed the tool."},
                {"step": 1, "phase": "Observe", "detail": "Observed the result."},
                {"step": 1, "phase": "Adapt", "detail": "Produced the answer."},
            ],
            "completed": True,
        }

    monkeypatch.setattr(backend_module, "run_agent_loop", fake_agent)
    response = client.post(
        "/api/ai/chat",
        json={"message": "What is outstanding?", "month": "2026-08", "history": []},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.get_json()["completed"] is True
    assert response.get_json()["trace"][2]["phase"] == "Observe"
    assert captured["month"] == "2026-08"
    assert captured["summary"]["received_total"] == 1020.0
    assert captured["outstanding"]["outstanding_total"] == 1500.0
    assert captured["outstanding"]["count"] == 2


def test_agent_loop_executes_tool_and_returns_visible_trace(monkeypatch):
    model_responses = iter(
        [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "get_outstanding_payments",
                                "arguments": {},
                            }
                        }
                    ],
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": "Two payments totalling AUD 1500.00 are outstanding.",
                }
            },
        ]
    )
    requested_urls = []

    def fake_post(url, **_kwargs):
        requested_urls.append(url)
        return FakeResponse(next(model_responses))

    observed_calls = []

    def execute_tool(name, arguments):
        observed_calls.append((name, arguments))
        return {"count": 2, "outstanding_total": 1500.0, "payments": []}

    monkeypatch.setattr(ai_service_module.requests, "post", fake_post)
    result = ai_service_module.run_agent_loop(
        "What is outstanding?",
        "2026-08",
        execute_tool,
        base_url="http://ollama.test/v1",
    )

    assert requested_urls == ["http://ollama.test/api/chat"] * 2
    assert observed_calls == [("get_outstanding_payments", {})]
    assert result["completed"] is True
    assert "AUD 1500.00" in result["answer"]
    assert {item["phase"] for item in result["trace"]} == {
        "Plan", "Act", "Observe", "Adapt"
    }


def test_generate_schedule_dates_from_frequency(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/pay-schedules/generate",
        json={"income_source_id": 1, "start_date": "2026-09-11", "count": 3},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    dates = [item["expected_pay_date"] for item in response.get_json()["items"]]
    assert dates == ["2026-09-11", "2026-09-25", "2026-10-09"]


def test_invalid_month_is_rejected(monkeypatch):
    client = make_client(monkeypatch)
    assert client.get(
        "/api/dashboard?month=August", headers=AUTH_HEADERS
    ).status_code == 400


def test_authentication_is_required(monkeypatch):
    client = make_client(monkeypatch)
    assert client.get("/api/income-sources").status_code == 401
    assert client.get(
        "/api/income-sources",
        headers={"Authorization": "Bearer invalid-token"},
    ).status_code == 401
