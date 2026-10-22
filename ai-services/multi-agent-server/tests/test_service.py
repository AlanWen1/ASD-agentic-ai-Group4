import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import service
from service import RunStore, create_app

def test_workflow_requires_human_decision_and_supports_correction(tmp_path, monkeypatch):
    def fake_call_model(model, system, user, timeout=None, **kwargs):
        if "You are the Planner" in system:
            return '{"objective":"test","steps":["inspect evidence"],"required_evidence":["items"],"checks":[],"risks":[],"assumptions":[],"success_criteria":["grounded"]}'
        if "independent Reviewer" in system:
            return '{"verdict":"pass","findings":[],"risks":[],"evidence_gaps":[],"recommendations":[],"plan_coverage":"covered"}'
        return "A grounded proposal using the supplied evidence."

    monkeypatch.setattr(service, "call_model", fake_call_model)
    app=create_app(RunStore(str(tmp_path/"runs.sqlite3"))); app.config["TESTING"]=True
    client=app.test_client(); headers={"X-Multi-Agent-Key":app.config["API_KEY"]}
    created=client.post("/runs",headers=headers,json={"module":"bills","user_id":"u1","task":"Prioritise bills","evidence":{"bills":[{"name":"Power","status":"Pending"}]}})
    assert created.status_code==201
    run=created.get_json(); assert run["status"]=="awaiting_human_review"; assert run["plan"]["objective"]=="test"; assert run["review"]["verdict"]=="pass"
    assert client.post("/runs/"+run["run_id"]+"/decision",json={"module":"bills","user_id":"u1","decision":"approve"}).status_code==401
    corrected=client.post("/runs/"+run["run_id"]+"/decision",headers=headers,json={"module":"bills","user_id":"u1","decision":"correct","feedback":"Show amounts in a table"})
    assert corrected.status_code==200; assert corrected.get_json()["status"]=="awaiting_human_review"; assert corrected.get_json()["correction_count"]==1
    approved=client.post("/runs/"+run["run_id"]+"/decision",headers=headers,json={"module":"bills","user_id":"u1","decision":"approve"})
    assert approved.status_code==200; assert approved.get_json()["status"]=="approved"; assert len(approved.get_json()["history"])==2

def test_validation_and_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(service,"call_model",lambda model,system,user,timeout=180,**kwargs:'{"ok": true}')    
    app=create_app(RunStore(str(tmp_path/"runs.sqlite3"))); app.config["TESTING"]=True
    client=app.test_client(); headers={"X-Multi-Agent-Key":app.config["API_KEY"]}
    bad=client.post("/runs",headers=headers,json={"module":"finance","user_id":"x","task":"test","evidence":{}})
    assert bad.status_code==400
    created=client.post("/runs",headers=headers,json={"module":"savings","user_id":"x","task":"test","evidence":{"goals":[]}}).get_json()
    assert client.get("/runs/"+created["run_id"]+"?module=savings&user_id=other",headers=headers).status_code==404
    assert client.post("/runs/"+created["run_id"]+"/decision",headers=headers,json={"module":"savings","user_id":"other","decision":"approve"}).status_code==404


def test_call_model_consumes_stream_and_uses_configured_limits(monkeypatch):
    import json
    import service

    seen = {}
    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def raise_for_status(self):
            pass
        def iter_lines(self, decode_unicode=False):
            yield json.dumps({"message": {"content": '{"objective":'}})
            yield json.dumps({"message": {"content": '"streamed"}'}})
            yield json.dumps({"done": True})

    def fake_post(url, json=None, timeout=None, stream=None):
        seen.update({"url": url, "payload": json, "timeout": timeout, "stream": stream})
        return FakeResponse()

    monkeypatch.setattr(service.requests, "post", fake_post)
    result = service.call_model("qwen2.5:0.5b", "system", "user")
    assert result == '{"objective":"streamed"}'
    assert seen["payload"]["stream"] is True
    assert seen["payload"]["keep_alive"] == service.OLLAMA_KEEP_ALIVE
    assert seen["payload"]["options"]["num_predict"] == service.OLLAMA_NUM_PREDICT
    assert seen["timeout"] == (service.OLLAMA_CONNECT_TIMEOUT_SECONDS, service.OLLAMA_TIMEOUT_SECONDS)
    assert seen["stream"] is True


def test_income_review_receives_plan_and_records_all_agent_stages(tmp_path, monkeypatch):
    captured = {}
    def fake(model, system, prompt, **kwargs):
        if "You are the Planner" in system:
            return '{"steps":["Check every income schedule"],"success_criteria":["No source omitted"]}'
        if "independent Reviewer" in system:
            captured["review"] = prompt
            return '{"verdict":"pass"}'
        assert "income sources" in system and "one line per budget" not in system
        return "Facts: one income source."
    monkeypatch.setattr(service, "call_model", fake)
    app = create_app(RunStore(str(tmp_path / "runs.db")))
    client = app.test_client()
    headers = {"X-Multi-Agent-Key": app.config["API_KEY"]}
    run = client.post("/runs", headers=headers, json={"module":"income", "user_id":"31", "task":"Review income", "evidence":{}}).get_json()
    assert "Check every income schedule" in captured["review"]
    assert "No source omitted" in captured["review"]
    stages = {(e["stage"], e["event"]) for e in run["audit"]}
    for stage in ("planner", "worker", "reviewer"):
        assert (stage, "started") in stages and (stage, "completed") in stages
    assert run["status"] == "awaiting_human_review" and not run["decision"]
    approved = client.post("/runs/"+run["run_id"]+"/decision", headers=headers,
                           json={"module":"income", "user_id":"31", "decision":"approve"})
    assert approved.get_json()["audit"][-1]["event"] == "approve"
    assert client.post("/runs/"+run["run_id"]+"/decision", headers=headers,
        json={"module":"income", "user_id":"31", "decision":"reject"}).status_code == 409


def test_savings_specific_review_preserves_plan_correction_and_audit(tmp_path, monkeypatch):
    calls = []

    def fake(model, system, prompt, **kwargs):
        calls.append((system, prompt, kwargs))
        if "You are the Planner" in system:
            return '{"steps":["Review every real goal"],"success_criteria":["No invented savings goals"]}'
        if "independent Reviewer" in system:
            return '{"verdict":"needs_attention","findings":["Deadline needs review"]}'
        return "Goal: Travel. Target amount: 2000. Current amount: 500."

    monkeypatch.setattr(service, "call_model", fake)
    app = create_app(RunStore(str(tmp_path / "runs.db")))
    client = app.test_client()
    headers = {"X-Multi-Agent-Key": app.config["API_KEY"]}
    response = client.post("/runs", headers=headers, json={
        "module": "savings", "user_id": "5", "task": "Review my savings goals",
        "evidence": {"goals": [{"name": "Travel", "target_amount": 2000, "current_amount": 500}]},
    })
    assert response.status_code == 201
    run = response.get_json()
    assert "Savings Goal Manager" in calls[0][0]
    assert "progress percentage, remaining amount" in calls[1][0]
    assert "Never add placeholder goals" in calls[1][0]
    assert calls[1][2]["num_predict"] == 1200
    assert "No invented savings goals" in calls[2][1]
    assert "invented, duplicate, placeholder" in calls[2][0]
    assert run["status"] == "awaiting_human_review" and not run["decision"]

    corrected = client.post("/runs/" + run["run_id"] + "/decision", headers=headers, json={
        "module": "savings", "user_id": "5", "decision": "correct",
        "feedback": "Explain the missing target date",
    })
    assert corrected.status_code == 200
    for _, prompt, _ in calls[-2:]:
        assert "Explain the missing target date" in prompt
        assert "No invented savings goals" in prompt
    assert any(event["stage"] == "reviewer" and event["event"] == "completed"
               and event["cycle"] == 1 for event in corrected.get_json()["audit"])
