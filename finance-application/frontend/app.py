import os

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:5000").rstrip("/")


@app.get("/")
def index():
    return render_template("index.html")


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
