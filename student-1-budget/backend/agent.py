import json
import requests
import os

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
DATABASE_URL = os.environ.get("DATABASE_URL", "http://budget-database:6001")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_budgets",
            "description": "Get all budgets for the current user.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_categories",
            "description": "Get all categories (with allocated amounts) for a specific budget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "integer", "description": "The budget ID to fetch categories for."}
                },
                "required": ["budget_id"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a budgeting assistant embedded in a personal finance app.
You can call tools to fetch the user's real budget and category data — never invent numbers.
When asked to review a budget, check whether any category's allocated_amount looks
unrealistic (e.g. a single category taking over 70% of the total, or an amount of $0
for something essential like rent/food). Explain briefly why something looks off.
Keep answers short and concrete. Always base answers only on tool results, not assumptions."""


def get_budgets(user_id):
    """Fetch budgets via budget-database's REST API, not direct SQLite access."""
    try:
        resp = requests.get(
            f"{DATABASE_URL}/api/budgets", params={"user_id": int(user_id)}, timeout=5
        )
        resp.raise_for_status()
        budgets = resp.json()
        return [
            {"budget_id": b["budget_id"], "month": b["month"], "year": b["year"], "status": b["status"]}
            for b in budgets
        ]
    except requests.exceptions.RequestException as e:
        return {"error": f"Could not reach budget-database: {e}"}


def get_categories(user_id, budget_id):
    """Fetch categories via budget-database's REST API, checking ownership first."""
    try:
        budget_resp = requests.get(f"{DATABASE_URL}/api/budgets/{budget_id}", timeout=5)
        if budget_resp.status_code == 404:
            return {"error": "Budget not found."}
        budget_resp.raise_for_status()
        if budget_resp.json().get("user_id") != int(user_id):
            return {"error": "Budget not found or not owned by this user."}

        cat_resp = requests.get(f"{DATABASE_URL}/api/budgets/{budget_id}/categories", timeout=5)
        cat_resp.raise_for_status()
        categories = cat_resp.json()
        return [
            {"category_name": c["category_name"], "allocated_amount": c["allocated_amount"], "notes": c["notes"]}
            for c in categories
        ]
    except requests.exceptions.RequestException as e:
        return {"error": f"Could not reach budget-database: {e}"}


def _call_tool(name, args, user_id):
    if name == "get_budgets":
        return get_budgets(user_id)
    if name == "get_categories":
        return get_categories(user_id, args.get("budget_id"))
    return {"error": f"Unknown tool {name}"}


def run_agent_loop(user_message, user_id, max_steps=4):
    """Plan -> Act -> Observe -> Adapt loop using Ollama tool calling."""
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

    return {"answer": "I wasn't able to finish reasoning about that in time — try a more specific question.", "trace": trace}
