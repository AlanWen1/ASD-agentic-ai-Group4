import json
import os
from datetime import date

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL", "http://bill-database:6004").rstrip("/")
AUTH_DATABASE_URL = os.environ.get("AUTH_DATABASE_URL", "http://finance-database:6000").rstrip("/")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
HTTP_TIMEOUT = 20


def service_request(base, method, path, **kwargs):
    try:
        return requests.request(method, f"{base}{path}", timeout=HTTP_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        app.logger.error("Service unavailable: %s", exc)
        return None


def current_user():
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        return None, (jsonify({"error": "Authentication required"}), 401)
    response = service_request(AUTH_DATABASE_URL, "GET", f"/sessions/{token}")
    if response is None:
        return None, (jsonify({"error": "Finance authentication service unavailable"}), 503)
    if not response.ok:
        return None, (jsonify({"error": "Invalid or expired session"}), 401)
    return response.json()["user"], None


def get_bills(user_id):
    response = service_request(DATABASE_URL, "GET", "/bills", params={"user_id": user_id})
    if response is None or not response.ok:
        raise RuntimeError("Bill database service is unavailable")
    return response.json()


def bill_context(bills):
    today = date.today()
    total = sum(float(b.get("amount", 0)) for b in bills)
    paid = sum(float(b.get("amount", 0)) for b in bills if b.get("status") == "Paid")
    pending = sum(float(b.get("amount", 0)) for b in bills if b.get("status") == "Pending")
    due_soon = []
    for bill in bills:
        try:
            due = date.fromisoformat(bill["due_date"])
            if 0 <= (due - today).days <= 7 and bill.get("status") != "Paid":
                due_soon.append(bill)
        except (KeyError, ValueError):
            pass
    return {
        "today": str(today), "bill_count": len(bills), "total_amount": round(total, 2),
        "paid_amount": round(paid, 2), "pending_amount": round(pending, 2),
        "overdue_count": sum(1 for b in bills if b.get("status") == "Overdue"),
        "due_within_7_days_count": len(due_soon), "bills": bills,
    }


def ask_ollama(message, context):
    prompt = ("You are the Bill Tracker assistant. Answer using ONLY the application context below. "
              "Do not invent bills, amounts, due dates, or statuses. You can calculate totals. "
              "Be concise and say when the context is insufficient.\n\nAPPLICATION CONTEXT:\n" + json.dumps(context, indent=2))
    payload = {"model": OLLAMA_MODEL, "stream": False, "messages": [
        {"role": "system", "content": prompt}, {"role": "user", "content": message[:4000]}
    ], "options": {"temperature": 0.2}}
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "No response from model.")
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach Ollama at {OLLAMA_URL}. Model '{OLLAMA_MODEL}' may be unavailable: {exc}") from exc


def forward_bill(method, path="", body=None, user_id=None):
    response = service_request(DATABASE_URL, method, f"/bills{path}", params={"user_id": user_id}, json=body)
    if response is None:
        return jsonify({"error": "Bill database service unavailable"}), 503
    try:
        data = response.json()
    except ValueError:
        data = {"error": response.text or "Bill database request failed"}
    return jsonify(data), response.status_code


@app.get("/health")
def health():
    database = service_request(DATABASE_URL, "GET", "/health")
    auth = service_request(AUTH_DATABASE_URL, "GET", "/health")
    ollama_ok = False
    try:
        ollama_ok = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).ok
    except requests.RequestException:
        pass
    ok = bool(database and database.ok and auth and auth.ok)
    return jsonify({"status": "ok" if ok else "degraded", "service": "bill-backend", "database": bool(database and database.ok), "finance_database": bool(auth and auth.ok), "ollama": ollama_ok, "ollama_model": OLLAMA_MODEL}), (200 if ok else 503)


@app.route("/bills", methods=["GET", "POST"])
def bills_collection():
    user, error = current_user()
    if error: return error
    if request.method == "GET": return forward_bill("GET", user_id=user["id"])
    return forward_bill("POST", body=request.get_json(silent=True) or {}, user_id=user["id"])


@app.route("/bills/<int:bill_id>", methods=["GET", "PUT", "DELETE"])
def bill_item(bill_id):
    user, error = current_user()
    if error: return error
    body = request.get_json(silent=True) if request.method == "PUT" else None
    return forward_bill(request.method, f"/{bill_id}", body=body, user_id=user["id"])


@app.get("/summary")
def summary():
    user, error = current_user()
    if error: return error
    response = service_request(DATABASE_URL, "GET", "/summary", params={"user_id": user["id"]})
    if response is None: return jsonify({"error": "Bill database service unavailable"}), 503
    return jsonify(response.json()), response.status_code


@app.post("/chat")
def chat():
    user, error = current_user()
    if error: return error
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message: return jsonify({"error": "message is required"}), 400
    try:
        bills = get_bills(user["id"])
        context = bill_context(bills)
        return jsonify({"answer": ask_ollama(message, context), "context": {"bill_count": context["bill_count"], "total_amount": context["total_amount"]}})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


@app.errorhandler(Exception)
def unhandled_error(exc):
    app.logger.exception("Unhandled bill-backend error")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004)
