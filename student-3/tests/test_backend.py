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


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


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


def fake_database_request(method, url, **kwargs):
    path = urlparse(url).path
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
    app = backend_module.create_app("http://database.test")
    app.config.update(TESTING=True)
    return app.test_client()


def test_dashboard_calculates_money_without_ai(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/dashboard?month=2026-08")
    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["expected_total"] == 2500.0
    assert summary["received_total"] == 1020.0
    assert summary["outstanding_total"] == 1500.0
    assert summary["variance"] == 20.0
    assert summary["late_count"] == 1


def test_ai_chat_receives_calculated_context(monkeypatch):
    client = make_client(monkeypatch)
    captured = {}

    def fake_ai(question, context, history=None):
        captured.update({"question": question, "context": context, "history": history})
        return "Your Job income is the largest source this month."

    monkeypatch.setattr(backend_module, "ask_ollama", fake_ai)
    response = client.post(
        "/api/ai/chat",
        json={"message": "What is my largest source?", "month": "2026-08", "history": []},
    )
    assert response.status_code == 200
    assert "largest" in response.get_json()["answer"]
    assert captured["context"]["summary"]["received_total"] == 1020.0


def test_generate_schedule_dates_from_frequency(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/pay-schedules/generate",
        json={"income_source_id": 1, "start_date": "2026-09-11", "count": 3},
    )
    assert response.status_code == 201
    dates = [item["expected_pay_date"] for item in response.get_json()["items"]]
    assert dates == ["2026-09-11", "2026-09-25", "2026-10-09"]


def test_invalid_month_is_rejected(monkeypatch):
    client = make_client(monkeypatch)
    assert client.get("/api/dashboard?month=August").status_code == 400
