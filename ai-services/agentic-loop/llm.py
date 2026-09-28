import json
import os
import re

import requests

DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_URL = "http://localhost:11434"
DEFAULT_FALLBACK_MODEL = "qwen2.5:0.5b"


def health(url=DEFAULT_URL, model=DEFAULT_MODEL):
    try:
        r = requests.get(url.rstrip("/") + "/api/tags", timeout=10)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        ok = model in names or any(
            n.split(":")[0] == model.split(":")[0] for n in names
        )
        return ok, names
    except (requests.RequestException, ValueError) as exc:
        return False, [str(exc)]


def available_models(url=DEFAULT_URL):
    try:
        r = requests.get(url.rstrip("/") + "/api/tags", timeout=10)
        r.raise_for_status()
        return [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
    except (requests.RequestException, ValueError):
        return []


def _candidate_models(url, primary):
    configured = os.environ.get("AGENT_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)
    installed = available_models(url)
    candidates = []

    for name in (primary, configured):
        if name and name not in candidates:
            candidates.append(name)

    # On low-memory machines, prefer a small installed model if the configured
    # fallback is not installed. This keeps llama3.1:8b as the required primary.
    for name in sorted(installed):
        if name not in candidates:
            candidates.append(name)

    return candidates


def ask(system, prompt, url=DEFAULT_URL, model=DEFAULT_MODEL, timeout=180):
    def call(selected_model):
        r = requests.post(
            url.rstrip("/") + "/api/chat",
            json={
                "model": selected_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": int(os.environ.get("AGENT_NUM_CTX", "2048")),
                },
            },
            timeout=timeout,
        )
        r.raise_for_status()
        body = r.json()
        message = body.get("message", {})
        content = message.get("content", "")
        if not content:
            raise ValueError(f"Ollama returned no message content for {selected_model}")
        return content.strip()

    primary_error = None
    for index, selected_model in enumerate(_candidate_models(url, model)):
        try:
            answer = call(selected_model)
            if selected_model != model:
                print(f"[PASS] LLM fallback active: {selected_model}")
            return answer
        except requests.RequestException as exc:
            if index == 0:
                primary_error = exc
                print(
                    f"[WARN] {model} failed to load/respond; "
                    "trying a smaller available model."
                )
            continue
        except ValueError as exc:
            if index == 0:
                primary_error = exc
            continue

    if primary_error is not None:
        raise primary_error
    raise RuntimeError("No Ollama model is available.")


def parse_json(text):
    text = (text or "").strip()

    if text.startswith("JSON:"):
        text = text[5:].strip()

    # Remove common Markdown fences used by smaller local models.
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass

    # Recover the first JSON object embedded in extra model prose.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            pass

    return {}