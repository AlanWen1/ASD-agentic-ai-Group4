import os

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL", "http://database:6000").rstrip("/")
BILL_DATABASE_URL = os.environ.get("BILL_DATABASE_URL", "http://bill-database:6004").rstrip("/")
TIMEOUT = 20


def call(url, method="GET", **kwargs):
    try:
        return requests.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        app.logger.error("Service request failed: %s", exc)
        return None


def session_user(required=True):
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        if required:
            return None, (jsonify({"error": "Authentication required"}), 401)
        return None, None

    response = call(f"{DATABASE_URL}/sessions/{token}")
    if response is None:
        return None, (jsonify({"error": "Authentication service unavailable"}), 503)
    if not response.ok:
        return None, (jsonify({"error": "Invalid or expired session"}), 401)
    return response.json()["user"], None


@app.get("/health")
def health():
    database = call(f"{DATABASE_URL}/health")
    bill_database = call(f"{BILL_DATABASE_URL}/health")
    ok = bool(database and database.ok and bill_database and bill_database.ok)
    return jsonify({
        "status": "ok" if ok else "degraded",
        "service": "finance-backend",
        "database": bool(database and database.ok),
        "bill_database": bool(bill_database and bill_database.ok),
    }), (200 if ok else 503)


@app.post("/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    response = call(f"{DATABASE_URL}/users", "POST", json=payload)
    if response is None:
        return jsonify({"error": "Authentication database unavailable"}), 503
    return jsonify(response.json()), response.status_code


@app.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    response = call(f"{DATABASE_URL}/auth/login", "POST", json=payload)
    if response is None:
        return jsonify({"error": "Authentication database unavailable"}), 503
    return jsonify(response.json()), response.status_code


@app.post("/auth/logout")
def logout():
    payload = request.get_json(silent=True) or {}
    response = call(f"{DATABASE_URL}/auth/logout", "POST", json=payload)
    if response is None:
        return jsonify({"error": "Authentication database unavailable"}), 503
    return jsonify(response.json()), response.status_code


@app.get("/auth/me")
def me():
    user, error = session_user()
    if error:
        return error
    return jsonify({"user": user})


@app.put("/users/me")
def update_me():
    user, error = session_user()
    if error:
        return error
    response = call(f"{DATABASE_URL}/users/{user['id']}", "PUT", json=request.get_json(silent=True) or {})
    if response is None:
        return jsonify({"error": "Authentication database unavailable"}), 503
    return jsonify(response.json()), response.status_code


@app.errorhandler(Exception)
def unhandled_error(exc):
    app.logger.exception("Unhandled finance backend error")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
