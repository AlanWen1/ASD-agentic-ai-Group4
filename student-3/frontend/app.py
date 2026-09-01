"""Frontend microservice for the Income & Pay Schedule Manager."""

from __future__ import annotations

import os
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, render_template, request


def create_app(backend_url: str | None = None) -> Flask:
    base_dir = Path(__file__).resolve().parent

    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
    )

    app.config["BACKEND_SERVICE_URL"] = (
        backend_url
        or os.getenv(
            "BACKEND_SERVICE_URL",
            "http://student-3-backend:5003",
        )
    ).rstrip("/")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "healthy",
                "service": "student-3-frontend",
            }
        )

    @app.route(
        "/api/<path:path>",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    )
    def backend_proxy(path: str):
        headers = {}

        if request.content_type:
            headers["Content-Type"] = request.content_type
        if request.headers.get("Authorization"):
            headers["Authorization"] = request.headers["Authorization"]

        try:
            upstream = requests.request(
                request.method,
                f"{app.config['BACKEND_SERVICE_URL']}/api/{path}",
                params=request.args,
                data=request.get_data(),
                headers=headers,
                timeout=100,
            )
        except requests.RequestException as exc:
            return jsonify(
                {"error": f"Backend service is unavailable: {exc}"}
            ), 503

        excluded_headers = {
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        }

        response_headers = [
            (name, value)
            for name, value in upstream.headers.items()
            if name.lower() not in excluded_headers
        ]

        return Response(
            upstream.content,
            upstream.status_code,
            response_headers,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3003, debug=False)
