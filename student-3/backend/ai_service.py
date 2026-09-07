"""Ollama client and prompt guardrails for the Income Manager."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import requests


class AIServiceError(RuntimeError):
    """Raised when the local Ollama model cannot answer."""


SYSTEM_PROMPT = """You are the AI Income Assistant inside an educational personal budgeting prototype.
Answer only from the income sources, pay schedules, and calculated summary supplied in the DATA CONTEXT.
If the data does not support an answer, clearly say that the available income data is insufficient.
Never invent payments, dates, amounts, employers, or trends. Do not provide investment, tax, legal,
credit, or financial-product advice. You may explain income patterns and payment schedules in plain
language. Keep answers concise, practical, and under 160 words. Format Australian dollars as AUD."""

AGENT_SYSTEM_PROMPT = """You are the AI Income Assistant inside an educational personal budgeting prototype.
Use the supplied tools to answer questions about the selected dashboard month. For every question
about the user's records, call at least one tool before answering. Never invent payments, dates,
amounts, employers, or trends. Do not request or choose a user ID: the application scopes every tool
to the authenticated user. After observing tool results, either call another useful tool or provide a
concise final answer under 160 words. Do not provide investment, tax, legal, credit, or financial-product
advice. Format Australian dollars as AUD."""

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_month_summary",
            "description": "Get calculated expected, received, outstanding, variance, counts, and per-source totals for the selected month.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_outstanding_payments",
            "description": "Get scheduled and late payments, plus their calculated total, for the selected month.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_income_sources",
            "description": "Get the authenticated user's income sources and their active status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

ToolExecutor = Callable[[str, dict[str, Any]], Any]


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


def run_agent_loop(
    question: str,
    selected_month: str,
    execute_tool: ToolExecutor,
    history: list[dict[str, str]] | None = None,
    *,
    base_url: str | None = None,
    model: str | None = None,
    timeout_seconds: int | None = None,
    max_steps: int = 4,
) -> dict[str, Any]:
    """Run a visible Plan -> Act -> Observe -> Adapt loop with user-scoped tools."""
    ollama_base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")).rstrip("/")
    native_base_url = ollama_base_url[:-3] if ollama_base_url.endswith("/v1") else ollama_base_url
    model_name = model or os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    timeout = timeout_seconds or int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "system", "content": f"Selected dashboard month: {selected_month}"},
    ]
    for message in (history or [])[-6:]:
        role = message.get("role")
        content = str(message.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:1500]})
    messages.append({"role": "user", "content": question[:2000]})

    trace: list[dict[str, Any]] = []
    used_tool = False

    for step in range(1, max_steps + 1):
        trace.append(
            {
                "step": step,
                "phase": "Plan",
                "detail": "Qwen reviewed the question, selected month, and available income-data tools.",
            }
        )
        try:
            response = requests.post(
                f"{native_base_url}/api/chat",
                json={
                    "model": model_name,
                    "messages": messages,
                    "tools": AGENT_TOOLS,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=timeout,
            )
            response.raise_for_status()
            message = response.json()["message"]
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise AIServiceError(
                f"Ollama agent is unavailable or returned an invalid response: {exc}"
            ) from exc

        messages.append(message)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            answer = str(message.get("content", "")).strip()
            if not answer:
                raise AIServiceError("Ollama returned an empty agent response")
            trace.append(
                {
                    "step": step,
                    "phase": "Adapt",
                    "detail": (
                        "Qwen used the observed tool results to produce the final answer."
                        if used_tool
                        else "Qwen produced a response without requesting an income-data tool."
                    ),
                }
            )
            return {"answer": answer, "trace": trace, "completed": used_tool}

        for call in tool_calls:
            function = call.get("function", {})
            tool_name = str(function.get("name", ""))
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise AIServiceError("Ollama returned invalid tool arguments") from exc
            if not isinstance(arguments, dict):
                raise AIServiceError("Ollama returned invalid tool arguments")

            trace.append(
                {
                    "step": step,
                    "phase": "Act",
                    "tool": tool_name,
                    "detail": f"Executed {tool_name} for the authenticated user.",
                }
            )
            result = execute_tool(tool_name, arguments)
            used_tool = True
            trace.append(
                {
                    "step": step,
                    "phase": "Observe",
                    "tool": tool_name,
                    "detail": _summarise_observation(tool_name, result),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

        trace.append(
            {
                "step": step,
                "phase": "Adapt",
                "detail": "Returned the observations to Qwen so it could answer or select another tool.",
            }
        )

    return {
        "answer": "I could not complete the income analysis within the available reasoning steps. Please ask a more specific question.",
        "trace": trace,
        "completed": False,
    }


def _summarise_observation(tool_name: str, result: Any) -> str:
    if not isinstance(result, dict):
        return f"{tool_name} returned application data."
    if result.get("error"):
        return f"{tool_name} returned an error: {result['error']}"
    if tool_name == "get_month_summary":
        return (
            f"Observed expected AUD {float(result.get('expected_total', 0)):.2f}, "
            f"received AUD {float(result.get('received_total', 0)):.2f}, and "
            f"outstanding AUD {float(result.get('outstanding_total', 0)):.2f}."
        )
    if tool_name == "get_outstanding_payments":
        return (
            f"Observed {result.get('count', 0)} outstanding payments totalling "
            f"AUD {float(result.get('outstanding_total', 0)):.2f}."
        )
    if tool_name == "get_income_sources":
        return f"Observed {result.get('count', 0)} income sources."
    return f"{tool_name} returned application data."


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
