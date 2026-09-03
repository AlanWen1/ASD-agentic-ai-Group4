"""
Shared Ollama client for AI Services (ai-mode) — Release 0 requirement.

This is a new, opt-in shared module. It does NOT replace or modify any of
the existing per-backend Ollama calls in expense-category-tracker,
bill-tracker, or student-1-budget — those keep working exactly as they do
today. This module exists so that any backend written or refactored going
forward can import one tested implementation of "call the shared Ollama
runtime" instead of re-writing the same requests/timeout/error-handling
code a sixth time. Migrating the existing backends onto this module (if
the team wants to) is a separate follow-up decision, not something this
change makes for them.

Convention followed here: the native Ollama HTTP API (`OLLAMA_URL`,
`/api/generate`, `/api/chat`, `/api/tags`) — the same convention already
used by expense-category-tracker/backend/app.py,
expense-category-tracker/backend/agent.py, bill-tracker/backend/app.py,
and student-1-budget/backend/agent.py. student-3/backend/ai_service.py
instead talks to Ollama's OpenAI-compatible `/v1` surface via
`OLLAMA_BASE_URL` — a different (also legitimate) convention that this
module does not attempt to unify; that would be a separate discussion for
the team since it'd mean changing student-3's code, which this change
deliberately leaves alone.
"""
import os

import requests

DEFAULT_URL = "http://host.docker.internal:11434"
DEFAULT_MODEL = "qwen2.5:0.5b"


class OllamaError(RuntimeError):
    """Raised when the shared Ollama runtime can't be reached or errors out."""


def _resolve_url(base_url=None):
    return (base_url or os.environ.get("OLLAMA_URL", DEFAULT_URL)).rstrip("/")


def _resolve_model(model=None):
    return model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)


def generate(prompt, *, model=None, base_url=None, timeout=30, options=None):
    """One-shot text completion via Ollama's `/api/generate`.

    Mirrors the pattern used today by
    expense-category-tracker/backend/app.py's `suggest_category` endpoint.
    Returns the plain response string (already `.strip()`-ed).
    """
    payload = {"model": _resolve_model(model), "prompt": prompt, "stream": False}
    if options:
        payload["options"] = options
    url = _resolve_url(base_url)
    try:
        response = requests.post(f"{url}/api/generate", json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(f"Could not reach Ollama at {url}: {exc}") from exc
    return response.json().get("response", "").strip()


def chat(messages, *, model=None, base_url=None, tools=None, timeout=60, options=None):
    """Multi-turn / tool-calling chat via Ollama's `/api/chat`.

    Mirrors the pattern used today by bill-tracker/backend/app.py and the
    Plan -> Act -> Observe -> Adapt agent loops in
    expense-category-tracker/backend/agent.py and
    student-1-budget/backend/agent.py.

    Returns the raw `message` dict from Ollama's response
    (`{"role": ..., "content": ..., "tool_calls": [...]}`) so a caller that
    already implements its own agent loop (tool dispatch, trace-building,
    max-step handling) can keep doing exactly that, unchanged — this
    function only replaces the HTTP plumbing around the call, not the loop
    logic itself.
    """
    payload = {"model": _resolve_model(model), "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    if options:
        payload["options"] = options
    url = _resolve_url(base_url)
    try:
        response = requests.post(f"{url}/api/chat", json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(f"Could not reach Ollama at {url}: {exc}") from exc
    return response.json()["message"]


def health_check(*, model=None, base_url=None, timeout=5):
    """Lightweight reachability check via `/api/tags`.

    Mirrors the inline `ollama_ok = requests.get(f"{OLLAMA_URL}/api/tags", ...)`
    check every backend's own `/health` route already does today. Never
    raises — a caller's `/health` endpoint can call this unconditionally.
    """
    url = _resolve_url(base_url)
    try:
        ok = requests.get(f"{url}/api/tags", timeout=timeout).ok
    except requests.RequestException:
        ok = False
    return {"ollama": ok, "ollama_model": _resolve_model(model), "ollama_url": url}
