"""
AI-Mode shared service — Release 0 requirement.

This is the actual shared AI-mode capability the project spec asks for:
one small Flask service that is the only thing in the whole application
that talks to the shared Ollama runtime directly. Every backend
(expense-category-tracker, bill-tracker, student-1-budget, student-3,
student-5) is pointed at this service instead of at Ollama itself (see
each service's OLLAMA_URL / OLLAMA_API_URL / OLLAMA_BASE_URL in
docker-compose.yml) — that's what makes the Ollama usage genuinely shared
rather than five separate integrations that merely happen to point at the
same host.

It exposes the exact same paths Ollama itself exposes for both API styles
already in use across the team's backends, and proxies each one straight
through to the real Ollama runtime, unchanged:

- Native API (used by expense-category-tracker, bill-tracker,
  student-1-budget, student-5): `/api/generate`, `/api/chat`, `/api/tags`.
- OpenAI-compatible API (used by student-3): `/v1/chat/completions`,
  `/v1/models`.

Because every path is a byte-for-byte proxy of Ollama's own response, no
existing backend code needed to change — only the URL each backend was
already pointed at (see docker-compose.yml). Centralising it here means
timeouts, error messages, and (later) things like an approved-model
allowlist or request logging only need to be implemented once, in
`ollama_client.py`, instead of five times.
"""
import os

from flask import Flask, jsonify, request

import ollama_client

app = Flask(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", ollama_client.DEFAULT_URL).rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", ollama_client.DEFAULT_MODEL)
OLLAMA_BASE_URL_V1 = os.environ.get("OLLAMA_BASE_URL", f"{OLLAMA_URL}/v1").rstrip("/")
PROXY_TIMEOUT = int(os.environ.get("AI_MODE_TIMEOUT", "120"))


def _proxy(method, upstream_base, path):
    """Forward the incoming request's JSON body/query params to `upstream_base +
    path` and mirror the upstream status code and JSON body back verbatim."""
    try:
        upstream = ollama_client.requests.request(
            method,
            f"{upstream_base}{path}",
            params=request.args,
            json=request.get_json(silent=True),
            timeout=PROXY_TIMEOUT,
        )
    except ollama_client.requests.RequestException as exc:
        return jsonify({"error": f"Could not reach shared Ollama runtime at {upstream_base}: {exc}"}), 502
    try:
        body = upstream.json()
    except ValueError:
        body = {"error": upstream.text or "Ollama returned a non-JSON response"}
    return jsonify(body), upstream.status_code


@app.get("/health")
def health():
    result = ollama_client.health_check(model=OLLAMA_MODEL, base_url=OLLAMA_URL)
    ok = result["ollama"]
    return jsonify({"status": "ok" if ok else "degraded", "service": "ai-mode", **result}), (200 if ok else 503)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    return _proxy("POST", OLLAMA_URL, "/api/generate")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    return _proxy("POST", OLLAMA_URL, "/api/chat")


@app.route("/api/tags", methods=["GET"])
def api_tags():
    return _proxy("GET", OLLAMA_URL, "/api/tags")


@app.route("/v1/chat/completions", methods=["POST"])
def v1_chat_completions():
    return _proxy("POST", OLLAMA_BASE_URL_V1, "/chat/completions")


@app.route("/v1/models", methods=["GET"])
def v1_models():
    return _proxy("GET", OLLAMA_BASE_URL_V1, "/models")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5099)))
