import os

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:5000").rstrip("/")


@app.get("/")
def index():
    modules = {name: os.getenv(name.upper() + "_FRONTEND_URL", os.getenv(name.upper() + "_URL", f"http://localhost:{port}/")).rstrip("/") + "/"
               for name, port in {"budget": 3001, "expense": 3002, "income": 3003, "bill": 3004, "savings": 3005}.items()}
    return render_template("index.html", module_urls=modules)


@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def proxy(path):
    headers = {}
    if request.headers.get("Authorization"):
        headers["Authorization"] = request.headers["Authorization"]
    try:
        response = requests.request(
            request.method,
            f"{BACKEND_URL}/{path}",
            params=request.args,
            json=request.get_json(silent=True) if request.method in {"POST", "PUT", "DELETE"} else None,
            headers=headers,
            timeout=30,
        )
        try:
            data = response.json()
            return jsonify(data), response.status_code
        except ValueError:
            return response.text, response.status_code, {"Content-Type": response.headers.get("Content-Type", "text/plain")}
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
    app.run(host="0.0.0.0", port=3000)
