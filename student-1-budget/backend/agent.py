import json
import requests
import sqlite3
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:7b"  # swap to "llama3.1" if that's what you pulled

DB_PATH = Path(__file__).parent.parent / "database" / "budget_manager.db"

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


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_budgets(student_id):
    conn = _get_db()
    rows = conn.execute(
        "SELECT budget_id, month, year, status FROM budgets WHERE student_id = ?",
        (student_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_categories(student_id, budget_id):
    conn = _get_db()
    owns = conn.execute(
        "SELECT 1 FROM budgets WHERE budget_id = ? AND student_id = ?",
        (budget_id, student_id),
    ).fetchone()
    if not owns:
        conn.close()
        return {"error": "Budget not found or not owned by this user."}
    rows = conn.execute(
        "SELECT category_name, allocated_amount, notes FROM budget_categories WHERE budget_id = ?",
        (budget_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _call_tool(name, args, student_id):
    if name == "get_budgets":
        return get_budgets(student_id)
    if name == "get_categories":
        return get_categories(student_id, args.get("budget_id"))
    return {"error": f"Unknown tool {name}"}


def run_agent_loop(user_message, student_id, max_steps=4):
    """Plan -> Act -> Observe -> Adapt loop using Ollama tool calling."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    trace = []

    for step in range(max_steps):
        response = requests.post(
            OLLAMA_URL,
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

            result = _call_tool(fn_name, fn_args, student_id)
            trace.append({"step": step, "type": "tool_call", "tool": fn_name, "args": fn_args})

            messages.append({
                "role": "tool",
                "content": json.dumps(result),
            })

    return {"answer": "I wasn't able to finish reasoning about that in time — try a more specific question.", "trace": trace}