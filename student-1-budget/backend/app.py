import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from agent import run_agent_loop
 
app = Flask(__name__)
CORS(app)
 
DATABASE_URL = os.environ.get("DATABASE_URL", "http://budget-database:6001")
AUTH_DATABASE_URL = os.environ.get("AUTH_DATABASE_URL", "http://finance-database:6000")
 
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
def current_user():
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        return None, (jsonify({"error": "Authentication required"}), 401)
    try:
        resp = requests.get(f"{AUTH_DATABASE_URL}/sessions/{token}", timeout=5)
    except requests.exceptions.RequestException:
        return None, (jsonify({"error": "Authentication service unavailable"}), 503)
    if not resp.ok:
        return None, (jsonify({"error": "Invalid or expired session"}), 401)
    return resp.json()["user"], None
 
 
def db_get(path, params=None):
    """GET request to the database service."""
    return requests.get(f"{DATABASE_URL}{path}", params=params, timeout=5)
 
 
def db_post(path, json=None):
    """POST request to the database service."""
    return requests.post(f"{DATABASE_URL}{path}", json=json, timeout=5)
 
 
def db_put(path, json=None):
    """PUT request to the database service."""
    return requests.put(f"{DATABASE_URL}{path}", json=json, timeout=5)
 
 
def db_delete(path):
    """DELETE request to the database service."""
    return requests.delete(f"{DATABASE_URL}{path}", timeout=5)
 
 
# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
 
@app.route("/api/agent/chat", methods=["POST"])
def agent_chat():
    user, err = current_user()
    if err: return err
    result = run_agent_loop(user_message, user["id"])
    
    body = request.get_json(silent=True) or {}
    user_message = body.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "message is required"}), 400
 
    try:
        result = run_agent_loop(user_message, student_id)
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
    if err: return err
    user_id = user["id"]  # integer e.g. 1
 
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
            "user_id": int(user_id),
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
    if err: return err
    user_id = user["id"]  # integer e.g. 1
 
    try:
        resp = db_get("/api/budgets", params={"user_id": int(user_id)})
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502
 
 
@app.route("/api/budgets/<int:budget_id>", methods=["GET"])
def get_budget(budget_id):
    user, err = current_user()
    if err: return err
    user_id = user["id"] 

    try:
        resp = db_get(f"/api/budgets/{budget_id}", params={"user_id": int(user_id)})
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502
 
 
@app.route("/api/budgets/<int:budget_id>", methods=["PUT"])
def update_budget(budget_id):
    user, err = current_user()
    if err: return err
    user_id = user["id"]  # integer e.g. 1
 
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
            "user_id": int(user_id),
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
    if err: return err
    user_id = user["id"]  # integer e.g. 1
 
    try:
        resp = db_delete(f"/api/budgets/{budget_id}?user_id={int(user_id)}")
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502
 
 
# ---------------------------------------------------------------------------
# Budget Categories CRUD — proxy to budget-database
# ---------------------------------------------------------------------------
 
@app.route("/api/budgets/<int:budget_id>/categories", methods=["POST"])
def create_category(budget_id):
    user, err = current_user()
    if err: return err
    user_id = user["id"]  # integer e.g. 1
 
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
            "user_id": int(user_id),
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
    if err: return err
    user_id = user["id"]  # integer e.g. 1
 
    try:
        resp = db_get(f"/api/budgets/{budget_id}/categories", params={"user_id": int(user_id)})
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach budget-database"}), 502
 
 
@app.route("/api/categories/<int:category_id>", methods=["PUT"])
def update_category(category_id):
    user, err = current_user()
    if err: return err
    user_id = user["id"]  # integer e.g. 1
 
    data = request.get_json(silent=True) or {}
    category_name = data.get("category_name")
    allocated_amount = data.get("allocated_amount")
    notes = data.get("notes")
 
    if allocated_amount is not None and float(allocated_amount) < 0:
        return jsonify({"error": "allocated_amount must be >= 0"}), 400
 
    try:
        resp = db_put(f"/api/categories/{category_id}", json={
            "user_id": int(user_id),
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
    if err: return err
    user_id = user["id"]  # integer e.g. 1
 
    try:
        resp = db_delete(f"/api/categories/{category_id}?user_id={int(user_id)}")
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
        "database": db_status
    }), 200


# ---------------------------------------------------------------------------
# Release 1: shared MCP + RAG server access.
# The frontend only ever calls these two routes on this backend.
# ---------------------------------------------------------------------------
RAG_SERVER_URL = os.environ.get("RAG_SERVER_URL", "http://rag-server:5101").rstrip("/")


@app.route("/api/mcp/query", methods=["POST"])
def mcp_query():
    """Call the shared MCP server's get_budgets tool for this user."""
    from mcp_client import call_mcp_tool
    user_id, err = get_user_id()
    if err:
        return err

    result = call_mcp_tool("get_budgets", user_id=user_id)
    status_code = 502 if isinstance(result, dict) and "error" in result else 200
    return jsonify({"tool": "get_budgets", "result": result}), status_code


@app.route("/api/rag/ask", methods=["POST"])
def rag_ask():
    """Forward a free-text question to the shared RAG server."""
    user_id, err = get_user_id()
    if err:
        return err

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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
 