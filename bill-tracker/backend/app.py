import json
import os
from datetime import date, timedelta

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "http://database:6004").rstrip("/")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
HTTP_TIMEOUT = 20


def db_request(method, path, **kwargs):
    try:
        response = requests.request(method, f"{DATABASE_URL}{path}", timeout=HTTP_TIMEOUT, **kwargs)
        return response
    except requests.RequestException as exc:
        app.logger.error("Database service unavailable: %s", exc)
        return None


def get_bills():
    response = db_request("GET", "/bills")
    if response is None:
        raise RuntimeError("Database service is unavailable")
    if not response.ok:
        raise RuntimeError(response.text or "Database request failed")
    return response.json()


def bill_context(bills):
    today = date.today()
    total = sum(float(bill.get("amount", 0)) for bill in bills)
    paid = sum(float(bill.get("amount", 0)) for bill in bills if bill.get("status") == "Paid")
    pending = sum(float(bill.get("amount", 0)) for bill in bills if bill.get("status") == "Pending")
    overdue = [bill for bill in bills if bill.get("status") == "Overdue"]
    due_soon = []
    for bill in bills:
        try:
            due = date.fromisoformat(bill["due_date"])
            if 0 <= (due - today).days <= 7 and bill.get("status") != "Paid":
                due_soon.append(bill)
        except (KeyError, ValueError):
            continue

    return {
        "today": str(today),
        "bill_count": len(bills),
        "total_amount": round(total, 2),
        "paid_amount": round(paid, 2),
        "pending_amount": round(pending, 2),
        "overdue_count": len(overdue),
        "due_within_7_days_count": len(due_soon),
        "bills": bills,
    }


def ask_ollama(message, context):
    system_prompt = (
        "You are the Bill Tracker assistant. Answer using ONLY the application context supplied below. "
        "Do not invent bills, amounts, due dates, or statuses. You can calculate totals from the supplied data. "
        "Be concise and helpful. If the context does not contain enough information, say so.\n\n"
        "APPLICATION CONTEXT:\n" + json.dumps(context, indent=2)
    )
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message[:4000]},
        ],
        "options": {"temperature": 0.2},
    }
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat", json=payload, timeout=120
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "No response from model.")
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_URL}. Make sure Ollama is running and "
            f"model '{OLLAMA_MODEL}' is available. Details: {exc}"
        ) from exc


@app.get("/health")
def health():
    db = db_request("GET", "/health")
    db_ok = bool(db and db.ok)
    ollama_ok = False
    try:
        ollama = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        ollama_ok = ollama.ok
    except requests.RequestException:
        pass
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "service": "backend",
        "database": db_ok,
        "ollama": ollama_ok,
        "ollama_model": OLLAMA_MODEL,
    }), (200 if db_ok else 503)


@app.route("/bills", methods=["GET", "POST"])
def bills_collection():
    if request.method == "GET":
        try:
            return jsonify(get_bills())
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 503

    response = db_request("POST", "/bills", json=request.get_json(silent=True))
    if response is None:
        return jsonify({"error": "Database service is unavailable"}), 503
    return jsonify(response.json()), response.status_code


@app.route("/bills/<int:bill_id>", methods=["GET", "PUT", "DELETE"])
def bill_item(bill_id):
    response = db_request(request.method, f"/bills/{bill_id}", json=(request.get_json(silent=True) if request.method == "PUT" else None))
    if response is None:
        return jsonify({"error": "Database service is unavailable"}), 503
    return jsonify(response.json()), response.status_code


@app.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    if len(message) > 4000:
        return jsonify({"error": "message must be 4000 characters or fewer"}), 400

    try:
        bills = get_bills()
        context = bill_context(bills)
        answer = ask_ollama(message, context)
        return jsonify({"answer": answer, "context": {
            "bill_count": context["bill_count"],
            "total_amount": context["total_amount"],
        }})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


@app.get("/summary")
def summary():
    try:
        bills = get_bills()
        return jsonify(bill_context(bills))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


@app.errorhandler(Exception)
def unhandled_error(exc):
    app.logger.exception("Unhandled backend error")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004)
