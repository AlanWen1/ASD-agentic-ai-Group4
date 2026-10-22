import os

import requests
from flask import Flask, Response, render_template, request

app = Flask(__name__)


@app.after_request
def add_security_headers(response):
    """Cloud endpoint security: standard browser hardening headers on every
    response (no MIME sniffing, no framing/clickjacking, no Referer leaking the
    ?token= handoff URL, HTTPS-only for a year). Browsers ignore HSTS on plain
    http://localhost, so local docker-compose runs are unaffected."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


# Where the real budget-backend lives. In local dev this is the docker-compose
# service name; in the cloud deployment, scripts/deploy/azure-deploy.sh rewrites
# it to the Container Apps internal hostname.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:5001")

# Where to send people for the shared Finance Application hub/login.
FINANCE_URL = os.environ.get("FINANCE_URL", "http://localhost:3000")

# Headers that must never be copied as-is between hops (RFC 7230 section 6.1),
# plus Host/Content-Length, which have to be recomputed for the new request.
_HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "content-encoding", "content-length", "host",
}


@app.route("/")
def index():
    return render_template("index.html", finance_url=FINANCE_URL)


@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_proxy(path):
    """Forward browser API calls on to budget-backend.

    budget-backend has no public ingress in the cloud deployment (only this
    frontend does), so static/app.js calls this server's own origin
    (API_BASE = "/api") and this route relays the request server-side, where
    the internal hostname in BACKEND_URL is actually reachable.
    """
    url = f"{BACKEND_URL}/api/{path}"
    forward_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }
    try:
        upstream = requests.request(
            method=request.method,
            url=url,
            headers=forward_headers,
            params=request.args,
            data=request.get_data(),
            # AI chat and Multi-Agent runs wait on the shared LLM, which can
            # take minutes on CPU; keep just under the Azure ingress 240s limit.
            timeout=230 if path.startswith(("agent/", "multi-agent/")) else 60,
        )
    except requests.RequestException as exc:
        return {"error": f"Could not reach budget-backend: {exc}"}, 502

    response_headers = [
        (key, value)
        for key, value in upstream.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    ]
    return Response(upstream.content, status=upstream.status_code, headers=response_headers)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=3001)
