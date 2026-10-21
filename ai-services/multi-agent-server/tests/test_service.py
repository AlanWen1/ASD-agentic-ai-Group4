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