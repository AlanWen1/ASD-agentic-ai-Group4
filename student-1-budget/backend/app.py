import os
import requests
import calendar
from flask import Flask, request, jsonify
from flask_cors import CORS
from agent import run_agent_loop


app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL", "http://budget-database:6001").rstrip("/")
AUTH_DATABASE_URL = os.environ.get("AUTH_DATABASE_URL", "http://finance-database:6000").rstrip("/")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def current_user():
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        return None, (jsonify({"error": "Authentication required"}), 401)
    response = requests.get(f"{AUTH_DATABASE_URL}/sessions/{token}", timeout=5)
    if response is None:
        return None, (jsonify({"error": "Finance authentication service unavailable"}), 503)
    if not response.ok:
        return None, (jsonify({"error": "Invalid or expired session"}), 401)
    return response.json()["user"], None


def db_get(path, params=None):
    return requests.get(f"{DATABASE_URL}{path}", params=params, timeout=5)

def db_post(path, json=None):
    return requests.post(f"{DATABASE_URL}{path}", json=json, timeout=5)

def db_put(path, json=None):
    return requests.put(f"{DATABASE_URL}{path}", json=json, timeout=5)

def db_delete(path):
    return requests.delete(f"{DATABASE_URL}{path}", timeout=5)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@app.route("/api/agent/chat", methods=["POST"])
def agent_chat():
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    if not AI_ENABLED:
        return jsonify({"error": "AI-Mode is disabled in this environment"}), 503

    body = request.get_json(silent=True) or {}
    user_message = body.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "message is required"}), 400

    try:
        result = run_agent_loop(user_message, user_id)
        return jsonify(result), 200
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach Ollama. Is it running?"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Budgets CRUD — proxy to budget-database
# ---------------------------------------------------------------------------

@app.route("/api/budgets", methods=["POST"])
def create_budget():
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    data = request.get_json(silent=True) or {}
    month = data.get("month")
    year = data.get("year")
    status = data.get("status", "active")

    if month is None or year is None:
        return jsonify({"error": "month and year are required"}), 400
    if not (1 <= int(month) <= 12):
        return jsonify({"error": "month must be between 1 and 12"}), 400
    if status not in ("active", "archived"):
        return jsonify({"error": "status must be active or archived"}), 400

    try:
        resp = db_post("/api/budgets", json={
            "user_id": user_id,
            "month": month,
            "year": year,
            "status": status
        })
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502


@app.route("/api/budgets", methods=["GET"])
def list_budgets():
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    try:
        resp = db_get("/api/budgets", params={"user_id": user_id})
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502


@app.route("/api/budgets/<int:budget_id>", methods=["GET"])
def get_budget(budget_id):
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    try:
        resp = db_get(f"/api/budgets/{budget_id}", params={"user_id": user_id})
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502


@app.route("/api/budgets/<int:budget_id>", methods=["PUT"])
def update_budget(budget_id):
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    data = request.get_json(silent=True) or {}
    month = data.get("month")
    year = data.get("year")
    status = data.get("status")

    if month is not None and not (1 <= int(month) <= 12):
        return jsonify({"error": "month must be between 1 and 12"}), 400
    if status is not None and status not in ("active", "archived"):
        return jsonify({"error": "status must be active or archived"}), 400

    try:
        resp = db_put(f"/api/budgets/{budget_id}", json={
            "user_id": user_id,
            "month": month,
            "year": year,
            "status": status
        })
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502


@app.route("/api/budgets/<int:budget_id>", methods=["DELETE"])
def delete_budget(budget_id):
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    try:
        resp = db_delete(f"/api/budgets/{budget_id}?user_id={user_id}")
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502


# ---------------------------------------------------------------------------
# Budget Categories CRUD — proxy to budget-database
# ---------------------------------------------------------------------------

@app.route("/api/budgets/<int:budget_id>/categories", methods=["POST"])
def create_category(budget_id):
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]


    data = request.get_json(silent=True) or {}
    category_name = data.get("category_name")
    allocated_amount = data.get("allocated_amount")
    notes = data.get("notes")

    if not category_name or allocated_amount is None:
        return jsonify({"error": "category_name and allocated_amount are required"}), 400
    if float(allocated_amount) < 0:
        return jsonify({"error": "allocated_amount must be >= 0"}), 400

    try:
        resp = db_post(f"/api/budgets/{budget_id}/categories", json={
            "user_id": user_id,
            "category_name": category_name,
            "allocated_amount": allocated_amount,
            "notes": notes
        })
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502


@app.route("/api/budgets/<int:budget_id>/categories", methods=["GET"])
def list_categories(budget_id):
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    try:
        resp = db_get(f"/api/budgets/{budget_id}/categories", params={"user_id": user_id})
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502


@app.route("/api/categories/<int:category_id>", methods=["PUT"])
def update_category(category_id):
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    data = request.get_json(silent=True) or {}
    category_name = data.get("category_name")
    allocated_amount = data.get("allocated_amount")
    notes = data.get("notes")

    if allocated_amount is not None and float(allocated_amount) < 0:
        return jsonify({"error": "allocated_amount must be >= 0"}), 400

    try:
        resp = db_put(f"/api/categories/{category_id}", json={
            "user_id": user_id,
            "category_name": category_name,
            "allocated_amount": allocated_amount,
            "notes": notes
        })
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502


@app.route("/api/categories/<int:category_id>", methods=["DELETE"])
def delete_category(category_id):
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    try:
        resp = db_delete(f"/api/categories/{category_id}?user_id={user_id}")
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502
 
 
# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    # Also check if database is reachable
    try:
        db_resp = db_get("/api/health")
        db_status = db_resp.json().get("status", "unknown")
    except Exception:
        db_status = "unreachable"

    return jsonify({
        "status": "ok",
        "service": "budget-manager-backend",
        "database": db_status,
        "ai": "enabled" if AI_ENABLED else "disabled",
        "mcp": "enabled" if MCP_ENABLED else "disabled",
        "rag": "enabled" if RAG_ENABLED else "disabled"
    }), 200


# ---------------------------------------------------------------------------
# Release 1: shared MCP + RAG server access.
# The frontend only ever calls these two routes on this backend.
# AI-Mode, MCP and RAG can be disabled via env vars (set to false in CI/CD).
# ---------------------------------------------------------------------------
RAG_SERVER_URL = os.environ.get("RAG_SERVER_URL", "http://rag-server:5101").rstrip("/")
MCP_ENABLED = os.environ.get("MCP_ENABLED", "true").lower() == "true"
RAG_ENABLED = os.environ.get("RAG_ENABLED", "true").lower() == "true"
AI_ENABLED = os.environ.get("AI_ENABLED", "true").lower() == "true"

@app.route("/api/mcp/query", methods=["POST"])
def mcp_query():
    """Call the shared MCP server's get_budgets tool for this user."""
    from mcp_client import call_mcp_tool
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    if not MCP_ENABLED:
        return jsonify({"error": "MCP is disabled in this environment"}), 503

    result = call_mcp_tool("get_budgets", user_id=user_id)
    status_code = 502 if isinstance(result, dict) and "error" in result else 200
    return jsonify({"tool": "get_budgets", "result": result}), status_code

@app.route("/api/mcp/overview", methods=["POST"])
def mcp_overview():
    """Call the shared MCP server's get_budget_overview tool for this user."""
    from mcp_client import call_mcp_tool
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    if not MCP_ENABLED:
        return jsonify({"error": "MCP is disabled in this environment"}), 503

    result = call_mcp_tool("get_budget_overview", user_id=user_id, status="active")
    status_code = 502 if isinstance(result, dict) and "error" in result else 200
    return jsonify({"tool": "get_budget_overview", "result": result}), status_code

@app.route("/api/rag/ask", methods=["POST"])
def rag_ask():
    """Forward a free-text question to the shared RAG server."""
    user, err = current_user()
    if err:
        return err
    user_id = user["id"]

    if not RAG_ENABLED:
        return jsonify({"error": "RAG is disabled in this environment"}), 503

    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()
    if not question:
        return jsonify({"error": "message is required"}), 400

    try:
        response = requests.post(
            f"{RAG_SERVER_URL}/answer_question",
            json={"query": question},
            timeout=20,
        )
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as exc:
        return jsonify({"error": f"RAG server unavailable: {exc}"}), 502



# Release 2: shared Planner / Worker / Reviewer workflow.
MULTI_AGENT_URL = os.getenv("MULTI_AGENT_URL", "http://host.docker.internal:5102").rstrip("/")
MULTI_AGENT_API_KEY = os.getenv("MULTI_AGENT_API_KEY", "local-dev-key-change-me")
MULTI_AGENT_ENABLED = os.getenv("MULTI_AGENT_ENABLED", "true").strip().lower() in {"true", "1", "yes", "on"}

def _multi_agent_call(method, path, **kwargs):
    if not MULTI_AGENT_ENABLED:
        return jsonify({"error": "Multi-Agent is disabled in this environment"}), 503
    try:
        upstream = requests.request(method, f"{MULTI_AGENT_URL}{path}",
            headers={"X-Multi-Agent-Key": MULTI_AGENT_API_KEY}, timeout=2100, **kwargs)
    except requests.RequestException as exc:
        return jsonify({"error": f"Multi-Agent Server unavailable: {exc}"}), 502
    try:
        payload = upstream.json()
    except ValueError:
        payload = {"error": "Multi-Agent Server returned invalid JSON"}
    return jsonify(payload), upstream.status_code

SHARE_FLAG_PCT = 40          # matches the Planner's "over 40%" step
ESSENTIAL_CATEGORIES = {"rent", "food", "groceries", "utilities"}

def build_budget_evidence(overview):
    """One clean source of truth: trimmed budgets, a text summary, and flags computed in code."""
    budgets, lines, flags = [], [], []
    for b in overview:
        month = int(b["month"])
        label = f"{calendar.month_name[month] if 1 <= month <= 12 else month} {b['year']}"
        total = float(b.get("total_allocated") or 0)
        cats = [{"category_name": c["category_name"],
                 "allocated_amount": float(c["allocated_amount"] or 0),
                 "share_pct": float(c.get("share_pct") or 0)} for c in b.get("categories", [])]
        budgets.append({"budget_id": b["budget_id"], "month": month, "year": b["year"],
                        "total_allocated": total, "categories": cats})
        cat_text = ", ".join(f"{c['category_name']} ${c['allocated_amount']:.2f} ({c['share_pct']}%)" for c in cats) or "no categories"
        lines.append(f"- {label} (budget {b['budget_id']}): total ${total:.2f} - {cat_text}")
        if not cats:
            flags.append(f"{label} (budget {b['budget_id']}): has no categories")
        for c in cats:
            if c["share_pct"] > SHARE_FLAG_PCT:
                flags.append(f"{label} (budget {b['budget_id']}): {c['category_name']} is {c['share_pct']}% of ${total:.2f}")
            if c["allocated_amount"] == 0 and c["category_name"].strip().lower() in ESSENTIAL_CATEGORIES:
                flags.append(f"{label} (budget {b['budget_id']}): {c['category_name']} is allocated $0")
    return {"source": "budget-database", "budgets": budgets,
            "summary_text": "\n".join(lines) or "(no active budgets)",
            "precomputed_flags": flags}


@app.route("/api/multi-agent/run", methods=["POST"])
def multi_agent_run():
    user, err = current_user()
    if err: return err
    body = request.get_json(silent=True) or {}
    task = str(body.get("task") or body.get("message") or "").strip()
    if not task: return jsonify({"error": "task is required"}), 400
    user_id = user["id"]
    try:
        resp = db_get("/api/budgets/overview", params={"user_id": user_id, "status": "active"})
        resp.raise_for_status()
        evidence = build_budget_evidence(resp.json())
    except Exception as exc:
        return jsonify({"error": f"Could not build budget evidence: {exc}"}), 502
    return _multi_agent_call("POST", "/runs", json={"module": "budget", "user_id": str(user_id), "task": task, "evidence": evidence})
        
@app.route("/api/multi-agent/runs", methods=["GET"])
def multi_agent_runs():
    user, err = current_user()
    if err: return err
    return _multi_agent_call("GET", "/runs", params={"module": "budget", "user_id": str(user["id"])})

@app.route("/api/multi-agent/runs/<run_id>/decision", methods=["POST"])
def multi_agent_decision(run_id):
    user, err = current_user()
    if err: return err
    body = request.get_json(silent=True) or {}
    decision = str(body.get("decision", "")).strip().lower()
    payload = {"module": "budget", "user_id": str(user["id"]), "decision": decision, "feedback": str(body.get("feedback", "")).strip()}
    return _multi_agent_call("POST", f"/runs/{run_id}/decision", json=payload)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5001)