"""Ollama client and prompt guardrails for the Income Manager."""

from __future__ import annotations

import os
from typing import Any

import requests


class AIServiceError(RuntimeError):
    """Raised when the local Ollama model cannot answer."""


SYSTEM_PROMPT = """You are the AI Income Assistant inside an educational personal budgeting prototype.
Answer only from the income sources, pay schedules, and calculated summary supplied in the DATA CONTEXT.
If the data does not support an answer, clearly say that the available income data is insufficient.
Never invent payments, dates, amounts, employers, or trends. Do not provide investment, tax, legal,
credit, or financial-product advice. You may explain income patterns and payment schedules in plain
language. Keep answers concise, practical, and under 160 words. Format Australian dollars as AUD."""


def ask_ollama(
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]] | None = None,
    *,
    base_url: str | None = None,
    model: str | None = None,
    timeout_seconds: int | None = None,
) -> str:
    ollama_base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")).rstrip("/")
    model_name = model or os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    timeout = timeout_seconds or int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))

    safe_history: list[dict[str, str]] = []
    for message in (history or [])[-6:]:
        role = message.get("role")
        content = str(message.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            safe_history.append({"role": role, "content": content[:1500]})

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": "DATA CONTEXT (trusted application data):\n" + _compact_context(context),
        },
        *safe_history,
        {"role": "user", "content": question[:2000]},
    ]

    try:
        response = requests.post(
            f"{ollama_base_url}/chat/completions",
            json={
                "model": model_name,
                "messages": messages,
                "stream": False,
                "temperature": 0.2,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        answer = payload["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIServiceError(
            f"Ollama is unavailable or returned an invalid response: {exc}"
        ) from exc
    if not answer:
        raise AIServiceError("Ollama returned an empty response")
    return answer


def check_ollama(
    *, base_url: str | None = None, model: str | None = None, timeout_seconds: int = 5
) -> dict[str, Any]:
    ollama_base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")).rstrip("/")
    selected_model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    try:
        response = requests.get(f"{ollama_base_url}/models", timeout=timeout_seconds)
        response.raise_for_status()
        models = [item.get("id", "") for item in response.json().get("data", [])]
        return {
            "available": True,
            "model": selected_model,
            "model_installed": selected_model in models,
            "models": models,
        }
    except (requests.RequestException, ValueError) as exc:
        return {"available": False, "model": selected_model, "error": str(exc)}


def _compact_context(context: dict[str, Any]) -> str:
    """Create a predictable text context without relying on the model for calculations."""
    summary = context.get("summary", {})
    lines = [
        f"Selected month: {summary.get('month', 'not supplied')}",
        f"Expected total: AUD {summary.get('expected_total', 0):.2f}",
        f"Received total: AUD {summary.get('received_total', 0):.2f}",
        f"Outstanding expected amount: AUD {summary.get('outstanding_total', 0):.2f}",
        f"Variance (actual minus expected for received payments): AUD {summary.get('variance', 0):.2f}",
        f"Received count: {summary.get('received_count', 0)}",
        f"Scheduled count: {summary.get('scheduled_count', 0)}",
        f"Late count: {summary.get('late_count', 0)}",
        f"Active income sources: {summary.get('active_source_count', 0)}",
        "Income totals by source:",
    ]
    for item in summary.get("by_source", []):
        lines.append(
            f"- {item['source_name']}: expected AUD {item['expected']:.2f}; "
            f"received AUD {item['received']:.2f}"
        )
    lines.append("Pay schedules in selected month:")
    for schedule in context.get("schedules", [])[:40]:
        actual = (
            f"AUD {float(schedule['actual_amount']):.2f} on {schedule['received_date']}"
            if schedule.get("actual_amount") is not None
            else "not received"
        )
        lines.append(
            f"- {schedule.get('expected_pay_date')}: {schedule.get('source_name')}, "
            f"expected AUD {float(schedule.get('expected_amount', 0)):.2f}, "
            f"status {schedule.get('status')}, actual {actual}"
        )
    return "\n".join(lines)
