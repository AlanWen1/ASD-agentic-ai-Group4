import os

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:5004").rstrip("/")


@app.get("/")
def index():
    return render_template("index.html")


@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def proxy(path):
    url = f"{BACKEND_URL}/{path}"
    try:
        response = requests.request(
            request.method,
            url,
            params=request.args,
            json=request.get_json(silent=True) if request.method in {"POST", "PUT"} else None,
            timeout=130 if path == "chat" else 30,
        )
        content_type = response.headers.get("Content-Type", "application/json")
        if "application/json" in content_type:
            return jsonify(response.json()), response.status_code
        return response.text, response.status_code, {"Content-Type": content_type}
    except requests.RequestException as exc:
        return jsonify({"error": f"Backend unavailable: {exc}"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3004)
