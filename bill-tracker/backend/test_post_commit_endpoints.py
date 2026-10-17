"""Post-commit endpoint smoke tests for Bill Tracker."""
from types import SimpleNamespace

import app as backend


def test_bills_collection_endpoint_is_user_scoped(monkeypatch):
    monkeypatch.setattr(backend, "current_user", lambda: ({"id": 44}, None))
    calls = []

    def fake_forward_bill(method, path="", body=None, user_id=None):
        calls.append((method, path, body, user_id))
        return backend.jsonify([{"bill_id": 5, "name": "Electricity"}]), 200

    monkeypatch.setattr(backend, "forward_bill", fake_forward_bill)
    response = backend.app.test_client().get("/bills")

    assert response.status_code == 200
    assert response.get_json()[0]["bill_id"] == 5
    assert calls == [("GET", "", None, 44)]


def test_summary_endpoint_returns_backend_summary(monkeypatch):
    monkeypatch.setattr(backend, "current_user", lambda: ({"id": 44}, None))
    summary = {"bill_count": 2, "total_amount": 145.5}
    monkeypatch.setattr(
        backend,
        "service_request",
        lambda base, method, path, **kwargs: SimpleNamespace(
            json=lambda: summary, status_code=200
        ),
    )

    response = backend.app.test_client().get("/summary")

    assert response.status_code == 200
    assert response.get_json() == summary