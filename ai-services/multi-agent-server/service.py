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
REVIEWER_MODEL = os.getenv("REVIEWER_MODEL", "qwen2.5:0.5b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("MULTI_AGENT_OLLAMA_TIMEOUT_SECONDS", "600"))
OLLAMA_CONNECT_TIMEOUT_SECONDS = int(os.getenv("MULTI_AGENT_OLLAMA_CONNECT_TIMEOUT_SECONDS", "10"))
OLLAMA_KEEP_ALIVE = os.getenv("MULTI_AGENT_OLLAMA_KEEP_ALIVE", "10m")
OLLAMA_NUM_PREDICT = int(os.getenv("MULTI_AGENT_OLLAMA_NUM_PREDICT", "1024"))
OLLAMA_NUM_CTX = int(os.getenv("MULTI_AGENT_OLLAMA_NUM_CTX", "8192"))
MAX_TASK_CHARS, MAX_EVIDENCE_CHARS, MAX_CORRECTIONS = 4000, 24000, 3

PLANNER_SYSTEM = (
    "You are the Planner for a personal finance app. Output ONLY one JSON object. "
    "Do NOT copy or repeat the evidence. Write a short plan for the task. Example:\n"
    '{"objective":"Review active budgets and flag unusual allocations",'
    '"steps":["List each active budget with month and total","Compare each category to the budget total","Flag categories over 40% or budgets with no categories"],'
    '"required_evidence":["budget list","category amounts"],"checks":["category shares sum to 100%"],'
    '"risks":["budgets with no categories"],"assumptions":[],"success_criteria":["every active budget is covered"]}'
)

def summarise_evidence(evidence):
    if isinstance(evidence, dict):
        return {k: (f"list of {len(v)} items" if isinstance(v, list) else type(v).__name__) for k, v in evidence.items()}
    return type(evidence).__name__

def evidence_for_prompt(evidence):
    if isinstance(evidence, dict) and "summary_text" in evidence:
        flags = evidence.get("precomputed_flags") or []
        flag_text = "\n".join("- " + f for f in flags) or "- none"
        return "BUDGETS:\n" + evidence["summary_text"] + "\n\nFLAGS COMPUTED BY THE APPLICATION (verified):\n" + flag_text
    return compact_json(evidence, MAX_EVIDENCE_CHARS)

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

def call_model(model: str, system_prompt: str, user_prompt: str, timeout: int | None = None, json_mode: bool = False, num_predict: int | None = None) -> str:    
    request_timeout = timeout if timeout is not None else OLLAMA_TIMEOUT_SECONDS
    try:
        with requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": model,
            "stream": True,
            **({"format": "json"} if json_mode else {}),
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": 0.2,
                "num_predict": num_predict or OLLAMA_NUM_PREDICT,
                "repeat_penalty": 1.1,                
                "num_ctx": OLLAMA_NUM_CTX,
                "repeat_penalty": 1.1,
            },
        }, timeout=(OLLAMA_CONNECT_TIMEOUT_SECONDS, request_timeout), stream=True) as response:
            response.raise_for_status()
            parts = []
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AgentServiceError("Ollama returned an unreadable streaming response.") from exc
                if chunk.get("error"):
                    raise AgentServiceError(f"Ollama error for model {model!r}: {chunk['error']}")
                message = chunk.get("message") or {}
                piece = message.get("content", "")
                if isinstance(piece, str) and piece:
                    parts.append(piece)
            content = "".join(parts).strip()
            if not content:
                raise AgentServiceError(f"Model {model!r} returned an empty message.")
            return content
    except AgentServiceError:
        raise
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        raise AgentServiceError(
            f"Could not complete an Ollama request for model {model!r} at {OLLAMA_URL}. "
            f"Streaming timeout is {request_timeout}s (read timeout resets as chunks arrive). "
            f"Check Ollama is responsive and the model is available. ({exc})"
        ) from exc

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
        for key in fields:
            if key not in allowed: raise ValueError(f"Unsupported run field: {key}")
        field_values={key:(json.dumps(value,ensure_ascii=False,default=str) if key.endswith("_json") else value) for key,value in fields.items()}
        query="""UPDATE runs SET
            plan_json=CASE WHEN ? THEN ? ELSE plan_json END,
            worker_output=CASE WHEN ? THEN ? ELSE worker_output END,
            review_json=CASE WHEN ? THEN ? ELSE review_json END,
            status=CASE WHEN ? THEN ? ELSE status END,
            decision_json=CASE WHEN ? THEN ? ELSE decision_json END,
            correction_count=CASE WHEN ? THEN ? ELSE correction_count END,
            history_json=CASE WHEN ? THEN ? ELSE history_json END,
            updated_at=?
            WHERE run_id=?"""
        values=[]
        for key in ("plan_json","worker_output","review_json","status","decision_json","correction_count","history_json"):
            values.extend((key in field_values,field_values.get(key)))
        values.extend([utc_now(),run_id])
        with self.connect() as conn: conn.execute(query,values)
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
        evidence_text=evidence_for_prompt(run["evidence"]); plan=run.get("plan") or {}
        correction_note=f"\nHUMAN CORRECTION REQUEST:\n{feedback}" if feedback else ""
        worker_text=call_model(WORKER_MODEL,
            "You are the Worker agent for a personal finance application. Use ONLY the supplied evidence. Copy month, year, budget ids, category names and amounts exactly. Never invent numbers, months or names. Treat the FLAGS section as verified and do not recompute percentages. Do not repeat yourself. Write under 200 words in exactly three sections: 'Facts' (one line per budget), 'Flagged items' (from the FLAGS section, or 'none'), 'Suggestions' (at most 3 short bullets). Never write to databases or take actions; this is a proposal for human review.",
            "TASK:\n"+run["task"]+"\nPLAN STEPS:\n"+"\n".join("- "+str(s) for s in plan.get("steps",[]))+"\n\nEVIDENCE:\n"+evidence_text+correction_note,
            num_predict=500)
        review_text=call_model(REVIEWER_MODEL,
            "You are the independent Reviewer. Check the Worker output against the evidence: every figure and flag must appear in the evidence, and every verified flag should be mentioned. Do NOT repeat the Worker output. Return ONLY JSON with keys verdict ('pass' or 'needs_attention'), findings, risks, evidence_gaps, recommendations (each an array of at most 3 short distinct strings) and plan_coverage (one sentence). Example: "
            '{"verdict":"pass","findings":["All figures match the evidence"],"risks":[],"evidence_gaps":[],"recommendations":["Review the flagged category"],"plan_coverage":"All plan steps were covered."}',
            "TASK:\n"+run["task"]+"\n\nEVIDENCE:\n"+evidence_text+"\n\nWORKER OUTPUT:\n"+worker_text,
            json_mode=True, num_predict=400)
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
            planner_text=call_model(PLANNER_MODEL, PLANNER_SYSTEM,
                "MODULE: "+module+"\nUSER TASK:\n"+task+"\nEVIDENCE AVAILABLE (summary only):\n"+json.dumps(summarise_evidence(evidence)),
                json_mode=True)
            plan=parse_json_response(planner_text,"plan_text")
            allowed={"objective","steps","required_evidence","checks","risks","assumptions","success_criteria"}
            plan={k:v for k,v in plan.items() if k in allowed}
            for key,fallback in {"objective":task,"steps":[],"required_evidence":[],"checks":[],"risks":[],"assumptions":[],"success_criteria":[]}.items(): plan.setdefault(key,fallback)
            if not plan["steps"]:
                plan["steps"]=["Retrieve the supplied budget evidence","Compute totals and category shares from the evidence","Flag allocations that look unusual","Return a proposal for human review"]
                plan["fallback"]=True  # visible in the audit trail
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