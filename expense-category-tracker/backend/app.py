"""
Expense backend — no direct database access. Every category/expense
operation is forwarded over HTTP to expense-database. Only this service
talks to Ollama for the AI category suggestion. Mirrors the pattern used
in bill-tracker/backend (service_request + forward helpers, Ollama via
host.docker.internal).
"""
import os

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "http://expense-database:6002").rstrip("/")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
HTTP_TIMEOUT = 20

ALLOWED_CATEGORIES = [
    "Groceries", "Dining", "Transport", "Utilities",
    "Entertainment", "Shopping", "Health", "Travel",
    "Education", "Other",
]


def service_request(method, path, **kwargs):
    try:
        return requests.request(method, f"{DATABASE_URL}{path}", timeout=HTTP_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        app.logger.error("expense-database unavailable: %s", exc)
        return None


def forward(method, path, body=None, params=None):
    response = service_request(method, path, json=body, params=params)
    if response is None:
        return jsonify({"error": "Expense database service unavailable"}), 503
    if response.status_code == 204:
        return "", 204
    try:
        data = response.json()
    except ValueError:
        data = {"error": response.text or "Expense database request failed"}
    return jsonify(data), response.status_code


@app.get("/api/health")
def health():
    database = service_request("GET", "/health")
    ollama_ok = False
    try:
        ollama_ok = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).ok
    except requests.RequestException:
        pass
    ok = bool(database and database.ok)
    return jsonify({
        "status": "ok" if ok else "degraded",
        "service": "expense-backend",
        "database": bool(database and database.ok),
        "ollama": ollama_ok,
        "ollama_model": OLLAMA_MODEL,
    }), (200 if ok else 503)


# ---------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------

@app.route("/api/categories", methods=["GET", "POST"])
def categories():
    if request.method == "GET":
        return forward("GET", "/categories")
    return forward("POST", "/categories", body=request.get_json(silent=True) or {})


@app.route("/api/categories/<int:cat_id>", methods=["PUT", "DELETE"])
def category_item(cat_id):
    body = request.get_json(silent=True) if request.method == "PUT" else None
    return forward(request.method, f"/categories/{cat_id}", body=body)


# ---------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------

@app.route("/api/expenses", methods=["GET", "POST"])
def expenses():
    if request.method == "GET":
        params = {"category_id": request.args["category_id"]} if "category_id" in request.args else None
        return forward("GET", "/expenses", params=params)
    return forward("POST", "/expenses", body=request.get_json(silent=True) or {})


@app.route("/api/expenses/<int:expense_id>", methods=["GET", "PUT", "DELETE"])
def expense_item(expense_id):
    body = request.get_json(silent=True) if request.method == "PUT" else None
    return forward(request.method, f"/expenses/{expense_id}", body=body)


# ---------------------------------------------------------------------
# AI: Suggest Category (calls Ollama directly, same as bill-backend)
# ---------------------------------------------------------------------

@app.route("/api/expenses/suggest-category", methods=["POST"])
def suggest_category():
    data = request.get_json(silent=True) or {}
    description = data.get("description", "")
    merchant = data.get("merchant", "")

    prompt = (
        "You are a financial assistant that categorises personal expenses.\n"
        f"Allowed categories: {', '.join(ALLOWED_CATEGORIES)}.\n"
        f'Expense description: "{description}"\n'
        f'Merchant: "{merchant}"\n'
        "Respond with ONLY the single best matching category name from the "
        "allowed list above. Do not explain your answer. Do not add punctuation."
    )

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
    except requests.exceptions.RequestException as e:
        return jsonify({"category": "Other", "error": f"AI service unavailable: {str(e)}"}), 200

    matched = next((c for c in ALLOWED_CATEGORIES if c.lower() in raw.lower()), "Other")
    return jsonify({"category": matched, "raw_response": raw})


@app.errorhandler(Exception)
def unhandled_error(exc):
    app.logger.exception("Unhandled expense-backend error")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
