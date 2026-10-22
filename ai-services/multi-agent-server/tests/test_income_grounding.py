"""Income evidence checks are independent of the model's own verdict."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import service


def evidence(expected="1250.50", received="1200.00"):
    return {"income_sources": {"count": 1, "items": [{"id": 7, "source_name": "Contract"}]},
            "pay_schedules": {"items": [{"id": 9, "expected_amount": expected,
                "actual_amount": received, "status": "received"}]}}


def claims(expected="1250.50", received="1200.00", variance="-50.50"):
    return {"income_source_count": 1, "payment_count": 1, "expected_total": expected,
            "received_total": received, "variance": variance,
            "observations": ["The received payment is below the expected payment."],
            "suggestions": ["Check the payment difference with the payer."]}


def workflow(tmp_path, monkeypatch, worker, planner=None):
    calls = []
    def model(name, system, user, **kwargs):
        calls.append((system, user))
        if system == service.INCOME_PLANNER_SYSTEM:
            return json.dumps(planner or {"steps": [{"invented_amount": 230}],
                "required_evidence": ["budget list"], "checks": ["category shares sum to 100%"]})
        if system == service.INCOME_REVIEWER_SYSTEM:
            return json.dumps({"verdict": "pass", "findings": [], "risks": [],
                "evidence_gaps": [], "recommendations": [], "plan_coverage": "covered"})
        assert system == service.INCOME_WORKER_SYSTEM
        assert kwargs["json_mode"] is True
        return json.dumps(worker)
    monkeypatch.setattr(service, "call_model", model)
    app = service.create_app(service.RunStore(str(tmp_path / "runs.db")))
    client = app.test_client()
    headers = {"X-Multi-Agent-Key": app.config["API_KEY"]}
    response = client.post("/runs", headers=headers, json={"module": "income", "user_id": "owner",
                          "task": "Compare expected and received income", "evidence": evidence()})
    assert response.status_code == 201
    return client, headers, response.json, calls


def test_currency_math_uses_records_not_demo_constants():
    records = evidence("87.23", "80.01")
    records["pay_schedules"]["items"] += [
        {"expected_amount": "10.02", "actual_amount": None, "status": "scheduled"},
        {"expected_amount": "500", "actual_amount": None, "status": "cancelled"}]
    records["income_sources"]["count"] = 999  # Record list, not caller-provided count, is authoritative.
    facts = service.income_facts(records)
    assert facts["income_source_count"] == 1
    assert facts["payment_count"] == 3
    assert (facts["expected_total"], facts["received_total"], facts["variance"]) == ("97.25", "80.01", "-17.24")


def test_correct_income_workflow_is_grounded_and_still_needs_human(tmp_path, monkeypatch):
    client, headers, run, calls = workflow(tmp_path, monkeypatch, claims())
    assert len(calls) == 3
    assert run["plan"]["fallback"] is True
    assert all(isinstance(step, str) for step in run["plan"]["steps"])
    assert "budget" not in json.dumps(run["plan"]).lower()
    assert "APP_FACTS" in calls[1][1] and "-50.50" in calls[1][1]
    assert run["status"] == "awaiting_human_review" and run["decision"] is None
    assert run["review"]["application_checks"]["passed"] is True
    assert "AUD -50.50" in run["worker_output"]
    accepted = client.post(f"/runs/{run['run_id']}/decision", headers=headers,
                          json={"module": "income", "user_id": "owner", "decision": "approve"})
    assert accepted.status_code == 200 and accepted.json["status"] == "approved"


@pytest.mark.parametrize("change", [
    {"income_source_count": 2}, {"expected_total": 230, "received_total": 240, "variance": 10},
    {"variance": "50.50"}, {"expected_total": "NaN"},
    {"observations": ["The expected payment is $230."]},
    {"suggestions": ["Change the budget category allocation."]}])
def test_wrong_claims_cannot_pass_or_be_approved(tmp_path, monkeypatch, change):
    worker = claims(); worker.update(change)
    client, headers, run, _ = workflow(tmp_path, monkeypatch, worker)
    assert run["review"]["verdict"] == "needs_attention"
    assert run["review"]["application_checks"]["passed"] is False
    assert "Unverified Worker response" in run["worker_output"]
    response = client.post(f"/runs/{run['run_id']}/decision", headers=headers,
        json={"module": "income", "user_id": "owner", "decision": "approve"})
    assert response.status_code == 409


def test_missing_income_records_are_not_certified_as_empty():
    facts = service.income_facts({"income_sources": {"error": "unavailable"}, "pay_schedules": []})
    worker = claims("0.00", "0.00", "0.00"); worker.update(income_source_count=0, payment_count=0)
    assert service.check_income_worker(worker, facts)


def test_correction_preserves_bad_draft_and_rechecks_new_model_output(tmp_path, monkeypatch):
    wrong = claims(); wrong["expected_total"] = "230"
    client, headers, run, _ = workflow(tmp_path, monkeypatch, wrong)
    def corrected(name, system, user, **kwargs):
        if system == service.INCOME_WORKER_SYSTEM:
            assert "HUMAN CORRECTION REQUEST" in user
            return json.dumps(claims())
        return json.dumps({"verdict": "pass", "findings": [], "risks": [], "evidence_gaps": [],
                           "recommendations": [], "plan_coverage": "covered"})
    monkeypatch.setattr(service, "call_model", corrected)
    response = client.post(f"/runs/{run['run_id']}/decision", headers=headers,
        json={"module": "income", "user_id": "owner", "decision": "correct", "feedback": "Check the actual records."})
    assert response.status_code == 200
    assert response.json["correction_count"] == 1 and response.json["status"] == "awaiting_human_review"
    assert response.json["review"]["application_checks"]["passed"] is True
    assert response.json["history"][0]["review"]["application_checks"]["passed"] is False
