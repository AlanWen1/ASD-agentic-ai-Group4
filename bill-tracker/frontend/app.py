import os

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:5004").rstrip("/")


@app.get("/")
def index():
    return render_template("index.html", finance_url=os.getenv("FINANCE_URL", "http://localhost:3000/"))


@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def proxy(path):
    url = f"{BACKEND_URL}/{path}"
    try:
        headers = {}
        if request.headers.get("Authorization"):
            headers["Authorization"] = request.headers["Authorization"]
        response = requests.request(
            request.method,
            url,
            params=request.args,
            json=request.get_json(silent=True) if request.method in {"POST", "PUT"} else None,
            headers=headers,
            timeout=2100 if path.startswith("multi-agent/") else (130 if path == "chat" else 30),
        )
        content_type = response.headers.get("Content-Type", "application/json")
        if "application/json" in content_type:
            return jsonify(response.json()), response.status_code
        return response.text, response.status_code, {"Content-Type": content_type}
    except requests.RequestException as exc:
        return jsonify({"error": f"Backend unavailable: {exc}"}), 503




@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    if os.getenv("APP_ENV") == "cloud":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3004)