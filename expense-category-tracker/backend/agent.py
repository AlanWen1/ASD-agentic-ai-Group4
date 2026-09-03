"""
Expense assistant — a real Plan -> Act -> Observe -> Adapt agentic loop
(same pattern as student-1-budget/backend/agent.py, so the team has one
consistent approach): the model decides which tool to call, the tool is
actually invoked against expense-database, the real result is fed back to
the model, and the model decides whether to call another tool or give a
final answer — for up to `max_steps` rounds.

This is deliberately a second, separate feature from the existing
`/api/expenses/suggest-category` endpoint in app.py. That endpoint is a
narrow one-shot classifier (pick one category name for one expense) and is
left as-is; this module adds a free-form "ask about your spending"
assistant that can look at multiple things before answering, which is what
an actual Plan/Act/Observe/Adapt loop needs in order to have more than one
step.

Every tool call goes through expense-database and is scoped to the
authenticated user's user_id (see database/app.py's per-user isolation),
so the assistant can only ever see and reason about that user's own
expenses/categories.
"""
import json
import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
DATABASE_URL = os.environ.get("DATABASE_URL", "http://expense-database:6002").rstrip("/")
HTTP_TIMEOUT = 20

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_expenses",
            "description": "Get all of the current user's expenses, optionally filtered by category id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category_id": {
                        "type": "integer",
                        "description": "Only return expenses in this category id.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_categories",
            "description": "Get all of the current user's expense categories.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_by_category",
            "description": "Get the current user's total amount spent per category, highest first.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM_PROMPT = """You are a personal finance assistant embedded in an expense tracking app.
You can call tools to fetch the user's real expenses and categories — never invent numbers.
When asked about spending patterns, use the tools to ground your answer in the user's actual
data before answering. Keep answers short and concrete."""


def _get(path, user_id, params=None):
    query = dict(params or {})
    query["user_id"] = user_id
    response = requests.get(f"{DATABASE_URL}{path}", params=query, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_expenses(user_id, category_id=None):
    params = {"category_id": category_id} if category_id else None
    return _get("/expenses", user_id, params)


def get_categories(user_id):
    return _get("/categories", user_id)


def get_spending_by_category(user_id):
    expenses = get_expenses(user_id)
    totals = {}
    for expense in expenses:
        name = expense.get("category_name") or "Uncategorised"
        totals[name] = totals.get(name, 0) + (expense.get("amount") or 0)
    return sorted(
        ({"category": name, "total": round(total, 2)} for name, total in totals.items()),
        key=lambda row: row["total"],
        reverse=True,
    )


def _call_tool(name, args, user_id):
    if name == "get_expenses":
        return get_expenses(user_id, args.get("category_id"))
    if name == "get_categories":
        return get_categories(user_id)
    if name == "get_spending_by_category":
        return get_spending_by_category(user_id)
    return {"error": f"Unknown tool {name}"}


def run_agent_loop(user_message, user_id, max_steps=4):
    """Plan -> Act -> Observe -> Adapt loop using Ollama tool calling.

    Plan:    the model decides whether it needs data and which tool to call.
    Act:     that tool is actually invoked against expense-database.
    Observe: the real result is fed back to the model as a tool message.
    Adapt:   the model reconsiders — call another tool, or answer now.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    trace = []

    for step in range(max_steps):
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "tools": TOOLS,
                "stream": False,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        message = data["message"]
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            trace.append({"step": step, "type": "final_answer"})
            return {"answer": message.get("content", ""), "trace": trace}

        for call in tool_calls:
            fn_name = call["function"]["name"]
            fn_args = call["function"].get("arguments", {})
            if isinstance(fn_args, str):
                fn_args = json.loads(fn_args)

            result = _call_tool(fn_name, fn_args, user_id)
            trace.append({"step": step, "type": "tool_call", "tool": fn_name, "args": fn_args})

            messages.append({
                "role": "tool",
                "content": json.dumps(result),
            })

    return {
        "answer": "I wasn't able to finish reasoning about that in time — try a more specific question.",
        "trace": trace,
    }
