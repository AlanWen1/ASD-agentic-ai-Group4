"""Shared local Planner/Worker/Reviewer service for Release 2."""
from __future__ import annotations
import json, os, re, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests
from flask import Flask, jsonify, request

VALID_MODULES = {"budget", "expenses", "income", "bills", "savings"}
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "qwen2.5:0.5b")
WORKER_MODEL = os.getenv("WORKER_MODEL", "qwen2.5:0.5b")
REVIEWER_MODEL = os.getenv("REVIEWER_MODEL", "llama3.1:8b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MAX_TASK_CHARS, MAX_EVIDENCE_CHARS, MAX_CORRECTIONS = 4000, 24000, 3

class AgentServiceError(RuntimeError):
    """A model or downstream service could not complete the requested stage."""

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def compact_json(value: Any, limit: int) -> str:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return encoded if len(encoded) <= limit else encoded[:limit] + "\n...[truncated]"

def parse_json_response(content: str, fallback_key: str) -> dict[str, Any]:
    cleaned = re.sub(r"\s*\x60{3}$", "", re.sub(r"^\x60{3}(?:json)?\s*", "", (content or "").strip(), flags=re.I))
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict): return parsed
    except json.JSONDecodeError: pass
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict): return parsed
        except json.JSONDecodeError: pass
    return {fallback_key: cleaned or "The model returned an empty response."}

def call_model(model: str, system_prompt: str, user_prompt: str, timeout: int = 180) -> str:
    """Call Ollama directly; each agent has an independent role and configured model."""
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": model, "stream": False,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "options": {"temperature": 0.2},
        }, timeout=timeout)
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise AgentServiceError(f"Model {model!r} returned an empty message.")
        return content.strip()
    except AgentServiceError: raise
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        raise AgentServiceError(f"Could not complete an Ollama request for model {model!r} at {OLLAMA_URL}. Check Ollama and the model are available. ({exc})") from exc

class RunStore:
    """SQLite store persists proposed work and human decisions between requests."""
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("MULTI_AGENT_DB_PATH", str(Path(__file__).resolve().parent / "runs.sqlite3"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, module TEXT NOT NULL, user_id TEXT NOT NULL, task TEXT NOT NULL,
                evidence_json TEXT NOT NULL, plan_json TEXT, worker_output TEXT, review_json TEXT,
                status TEXT NOT NULL, decision_json TEXT, correction_count INTEGER NOT NULL DEFAULT 0,
                history_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10); conn.row_factory = sqlite3.Row; return conn
    def create(self, module, user_id, task, evidence):
        now, run_id = utc_now(), str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute("INSERT INTO runs (run_id,module,user_id,task,evidence_json,status,history_json,created_at,updated_at) VALUES (?,?,?,?,?,'planning','[]',?,?)",
                (run_id,module,str(user_id),task,json.dumps(evidence,ensure_ascii=False,default=str),now,now))
        return self.get(run_id)
    def get(self, run_id):
        with self.connect() as conn: row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._decode(row) if row else None
    def list_for(self, module, user_id, limit=10):
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM runs WHERE module=? AND user_id=? ORDER BY created_at DESC LIMIT ?",(module,str(user_id),limit)).fetchall()
        return [self._decode(row) for row in rows]
    def update(self, run_id, **fields):
        allowed={"plan_json","worker_output","review_json","status","decision_json","correction_count","history_json"}
        updates=[]; values=[]
        for key,value in fields.items():
            if key not in allowed: raise ValueError(f"Unsupported run field: {key}")
            updates.append(f"{key}=?")
            values.append(json.dumps(value,ensure_ascii=False,default=str) if key.endswith("_json") else value)
        updates.append("updated_at=?"); values.extend([utc_now(),run_id])
        with self.connect() as conn: conn.execute(f"UPDATE runs SET {', '.join(updates)} WHERE run_id=?",values)
        result=self.get(run_id)
        if result is None: raise KeyError(run_id)
        return result
    @staticmethod
    def _decode(row):
        run=dict(row)
        for key in ("evidence_json","plan_json","review_json","decision_json","history_json"):
            raw=run.pop(key,None); target=key.removesuffix("_json")
            try: run[target]=json.loads(raw) if raw else (None if target!="history" else [])
            except (TypeError,json.JSONDecodeError): run[target]=raw
        return run

def _owned_by_request(run, module, user_id):
    return str(module or "").strip().lower()==run["module"] and str(user_id or "").strip()==run["user_id"]

def create_app(store: RunStore | None = None):
    app=Flask(__name__); run_store=store or RunStore()
    app.config["API_KEY"]=os.getenv("MULTI_AGENT_API_KEY","local-dev-key-change-me")
    @app.before_request
    def require_local_client_key():
        if request.path=="/health": return None
        if request.headers.get("X-Multi-Agent-Key","") != app.config["API_KEY"]:
            return jsonify({"error":"Missing or invalid multi-agent API key"}),401
        return None

    def execute_worker_and_reviewer(run, feedback=""):
        evidence_text=compact_json(run["evidence"],MAX_EVIDENCE_CHARS); plan=run.get("plan") or {}
        correction_note=f"\nHUMAN CORRECTION REQUEST:\n{feedback}" if feedback else ""
        worker_text=call_model(WORKER_MODEL,
            "You are the Worker agent for a personal finance application. Follow the Planner plan and use only supplied application evidence. Do not invent transactions, amounts, dates or account details. Separate facts from suggestions. Never write to databases, execute transactions or take external actions; return a proposal for human review.",
            "MODULE: "+run["module"]+"\nTASK:\n"+run["task"]+"\nPLANNER PLAN:\n"+compact_json(plan,10000)+"\nSUPPLIED APPLICATION EVIDENCE:\n"+evidence_text+correction_note+"\nReturn proposed results, evidence references, calculations, assumptions and unresolved questions.")
        review_text=call_model(REVIEWER_MODEL,
            "You are the independent Reviewer. Compare Worker output with the Planner plan and supplied application evidence. Identify unsupported claims, arithmetic/date risks, privacy concerns, missing evidence and deviations. The model output is not itself evidence. Return JSON keys verdict (pass|needs_attention), findings (array), risks (array), evidence_gaps (array), recommendations (array), and plan_coverage (string).",
            "MODULE: "+run["module"]+"\nTASK:\n"+run["task"]+"\nPLAN:\n"+compact_json(plan,10000)+"\nEVIDENCE:\n"+evidence_text+"\nWORKER OUTPUT:\n"+worker_text+"\nReview strictly against evidence; do not silently rewrite Worker output.")
        review=parse_json_response(review_text,"review_text")
        for key,fallback in {"verdict":"needs_attention","findings":[],"risks":[],"evidence_gaps":[],"recommendations":[],"plan_coverage":"Inspect the raw review; it could not be fully structured."}.items(): review.setdefault(key,fallback)
        review["reviewer_model"]=REVIEWER_MODEL
        return run_store.update(run["run_id"],worker_output=worker_text,review_json=review,status="awaiting_human_review",decision_json=None)

    @app.get("/health")
    def health():
        return jsonify({"status":"ok","service":"multi-agent-server","containerised":False,"models":{"planner":PLANNER_MODEL,"worker":WORKER_MODEL,"reviewer":REVIEWER_MODEL},"ollama_url":OLLAMA_URL})
    @app.post("/runs")
    def create_run():
        body=request.get_json(silent=True) or {}; module=str(body.get("module","")).strip().lower()
        task=str(body.get("task","")).strip(); evidence=body.get("evidence",{}); user_id=str(body.get("user_id","")).strip()
        if module not in VALID_MODULES: return jsonify({"error":"module must be one of: "+", ".join(sorted(VALID_MODULES))}),400
        if not task: return jsonify({"error":"task is required"}),400
        if len(task)>MAX_TASK_CHARS: return jsonify({"error":f"task must be at most {MAX_TASK_CHARS} characters"}),400
        if not user_id: return jsonify({"error":"user_id is required"}),400
        if not isinstance(evidence,(dict,list,str)): return jsonify({"error":"evidence must be an object, array, or string"}),400
        if len(compact_json(evidence,MAX_EVIDENCE_CHARS+1))>MAX_EVIDENCE_CHARS: return jsonify({"error":f"evidence must be at most {MAX_EVIDENCE_CHARS} characters"}),413
        run=run_store.create(module,user_id,task,evidence)
        try:
            planner_text=call_model(PLANNER_MODEL,
                "You are the Planner for a personal finance application. Convert the task into a safe executable plan. Identify work, the supplied evidence required and fields to use, calculations/checks, risks, assumptions and unresolved questions. Never invent evidence, make transactions or modify accounts. Return JSON keys objective, steps (array), required_evidence (array), checks (array), risks (array), assumptions (array), success_criteria (array).",
                "MODULE: "+module+"\nUSER TASK:\n"+task+"\nAVAILABLE APPLICATION EVIDENCE:\n"+compact_json(evidence,MAX_EVIDENCE_CHARS)+"\nExplicitly list requested evidence that is missing.")
            plan=parse_json_response(planner_text,"plan_text")
            for key,fallback in {"objective":task,"steps":[],"required_evidence":[],"checks":[],"risks":[],"assumptions":[],"success_criteria":[]}.items(): plan.setdefault(key,fallback)
            plan["planner_model"]=PLANNER_MODEL
            run=run_store.update(run["run_id"],plan_json=plan,status="working")
            run=execute_worker_and_reviewer(run)
        except AgentServiceError as exc:
            run_store.update(run["run_id"],status="failed")
            return jsonify({"error":str(exc),"run":run_store.get(run["run_id"])}),503
        return jsonify(run),201
    @app.get("/runs")
    def list_runs():
        module=str(request.args.get("module","")).strip().lower(); user_id=str(request.args.get("user_id","")).strip()
        if module not in VALID_MODULES or not user_id: return jsonify({"error":"module and user_id filters are required"}),400
        return jsonify({"runs":run_store.list_for(module,user_id)})
    @app.get("/runs/<run_id>")
    def get_run(run_id):
        run=run_store.get(run_id)
        if not run or not _owned_by_request(run,request.args.get("module"),request.args.get("user_id")): return jsonify({"error":"run not found"}),404
        return jsonify(run)
    @app.post("/runs/<run_id>/decision")
    def human_decision(run_id):
        run=run_store.get(run_id)
        if not run: return jsonify({"error":"run not found"}),404
        body=request.get_json(silent=True) or {}
        if not _owned_by_request(run,body.get("module"),body.get("user_id")): return jsonify({"error":"run not found"}),404
        if run["status"]!="awaiting_human_review": return jsonify({"error":f"run is not awaiting human review (status: {run['status']})"}),409
        decision=str(body.get("decision","")).strip().lower(); feedback=str(body.get("feedback","")).strip()
        if decision not in {"approve","correct","reject"}: return jsonify({"error":"decision must be approve, correct, or reject"}),400
        if decision=="correct" and not feedback: return jsonify({"error":"feedback is required when requesting a correction"}),400
        history=list(run.get("history") or [])
        history.append({"at":utc_now(),"decision":decision,"feedback":feedback if decision=="correct" else "","worker_output":run.get("worker_output"),"review":run.get("review")})
        if decision=="approve":
            return jsonify(run_store.update(run_id,status="approved",decision_json={"decision":"approve","feedback":"","at":utc_now()},history_json=history))
        if decision=="reject":
            return jsonify(run_store.update(run_id,status="rejected",decision_json={"decision":"reject","feedback":feedback,"at":utc_now()},history_json=history))
        if int(run.get("correction_count") or 0)>=MAX_CORRECTIONS: return jsonify({"error":f"maximum of {MAX_CORRECTIONS} correction cycles reached"}),409
        run=run_store.update(run_id,status="correcting",correction_count=int(run.get("correction_count") or 0)+1,history_json=history,decision_json={"decision":"correct","feedback":feedback,"at":utc_now()})
        try: return jsonify(execute_worker_and_reviewer(run,feedback=feedback))
        except AgentServiceError as exc:
            run_store.update(run_id,status="failed")
            return jsonify({"error":str(exc),"run":run_store.get(run_id)}),503
    return app

app=create_app()
if __name__=="__main__":
    app.run(host=os.getenv("MULTI_AGENT_HOST","0.0.0.0"),port=int(os.getenv("MULTI_AGENT_PORT","5102")),debug=False)