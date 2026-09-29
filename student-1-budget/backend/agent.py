"""
Budget Manager agent — Plan -> Act -> Observe -> Adapt loop (Release 1).

Release 1 changes:
  * RAG: before the loop, the user's question is sent to the shared RAG
    server's /retrieve_context. The top-k knowledge-base chunks are injected
    into the system prompt so general budgeting / how-to answers are grounded
    in retrieved context and cite their source ids.
  * MCP: the agent's main tool, get_budget_overview, calls the shared MCP
    server (via mcp_client.call_mcp_tool). It returns every budget with its
    categories, total_allocated and share_pct in one call — computed by
    budget-database at read time, so the model does no arithmetic.
    If the MCP server is unreachable it falls back to budget-database's own
    /api/budgets/overview endpoint, and the trace records which path was used
    ("mcp" or "direct-fallback").
  * get_categories (one specific budget, e.g. an archived one) still calls
    budget-database directly — the shared MCP server has no such tool.
"""
import calendar
import json
import os

import requests

from mcp_client import call_mcp_tool

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:5099").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
DATABASE_URL = os.environ.get("DATABASE_URL", "http://budget-database:6001").rstrip("/")
RAG_SERVER_URL = os.environ.get("RAG_SERVER_URL", "http://host.docker.internal:5101").rstrip("/")
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "3"))

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_budget_overview",
            "description": (
                "Get the user's budgets with every category, its allocated_amount, "
                "its share_pct of the budget, and each budget's total_allocated. "
                "Use this for any question about the user's own budgets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "archived"],
                        "description": "Which budgets to fetch. Defaults to active.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_categories",
            "description": "Get the categories (with allocated amounts) for one specific budget_id.",
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
You have two sources of information:
1. The user's budget data (below) - their real active budgets, fetched live.
   Use it for any question about the user's budgets. Never invent numbers and
   never ask the user for figures that are already listed. For archived budgets,
   call get_budget_overview with status "archived".
2. Knowledge base excerpts (below) - use them for general budgeting guidance and
   questions about how the app works. When you use an excerpt, cite its id in
   square brackets, e.g. [faq-create-budget].
If neither source covers the question, say you don't have that information.
When asked to review a budget, flag any category with share_pct over 70, or an
allocated_amount of 0 for something essential like rent or food, and briefly
explain why.
Keep answers short and concrete. Do not give investment, tax or legal advice."""


# ---------------------------------------------------------------------------
# RAG — retrieval before generation
# ---------------------------------------------------------------------------

def _get_rag_context(query):
    """Return (context_block, source_ids, error). Never raises."""
    try:
        resp = requests.post(
            f"{RAG_SERVER_URL}/retrieve_context",
            json={"query": query, "k": RAG_TOP_K},
            timeout=10,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        return "", [], f"RAG server unavailable: {exc}"

    if data.get("status") != "success":
        return "", [], data.get("error", "Retrieval failed")

    results = data.get("results", [])
    block = "\n\n".join(f"[{r['source_id']}] {r['text']}" for r in results)
    return block, [r["source_id"] for r in results], None


# ---------------------------------------------------------------------------
# Tools — Act step
# ---------------------------------------------------------------------------

def _get_budget_overview_direct(user_id, status):
    """Fallback: the same overview straight from budget-database's REST API."""
    try:
        resp = requests.get(
            f"{DATABASE_URL}/api/budgets/overview",
            params={"user_id": user_id, "status": status},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        return {"error": f"Could not reach budget-database: {e}"}


def get_budget_overview(user_id, status="active"):
    """Fetch the overview through the shared MCP server. Returns (result, source)."""
    if status not in ("active", "archived"):
        status = "active"
    result = call_mcp_tool("get_budget_overview", user_id=user_id, status=status)
    if isinstance(result, list):
        return result, "mcp"
    # MCP unreachable or tool error: fall back so the demo keeps working,
    # and record it in the trace so it's visible.
    return _get_budget_overview_direct(user_id, status), "direct-fallback"


def _format_overview(overview):
    """Compact text version of the overview for the prompt - far easier for a
    small model to read than raw JSON, and much shorter."""
    if isinstance(overview, dict) and "error" in overview:
        return f"(could not load budget data: {overview['error']})"
    if not overview:
        return "(the user has no active budgets yet)"
    lines = []
    for b in overview:
        cats = ", ".join(
            f"{c['category_name']} ${float(c['allocated_amount']):.2f} ({c['share_pct']}%)"
            for c in b.get("categories", [])
        ) or "no categories yet"
        month = calendar.month_name[int(b["month"])] if 1 <= int(b["month"]) <= 12 else b["month"]
        lines.append(
            f"- {month} {b['year']} (budget_id {b['budget_id']}, {b['status']}): "
            f"total ${float(b['total_allocated']):.2f} - {cats}"
        )
    return "\n".join(lines)


def get_categories(user_id, budget_id):
    """Fetch categories via budget-database's REST API, checking ownership first."""
    try:
        budget_resp = requests.get(f"{DATABASE_URL}/api/budgets/{budget_id}", timeout=5)
        if budget_resp.status_code == 404:
            return {"error": "Budget not found."}
        budget_resp.raise_for_status()
        if str(budget_resp.json().get("user_id")) != str(user_id):
            return {"error": "Budget not found or not owned by this user."}

        cat_resp = requests.get(f"{DATABASE_URL}/api/budgets/{budget_id}/categories", timeout=5)
        cat_resp.raise_for_status()
        return [
            {"category_name": c["category_name"], "allocated_amount": c["allocated_amount"], "notes": c["notes"]}
            for c in cat_resp.json()
        ]
    except requests.exceptions.RequestException as e:
        return {"error": f"Could not reach budget-database: {e}"}


def _call_tool(name, args, user_id):
    """Returns (result, source)."""
    if name == "get_budget_overview":
        return get_budget_overview(user_id, args.get("status") or "active")
    if name == "get_categories":
        return get_categories(user_id, args.get("budget_id")), "direct"
    return {"error": f"Unknown tool {name}"}, "none"


# ---------------------------------------------------------------------------
# Plan -> Act -> Observe -> Adapt
# ---------------------------------------------------------------------------

def run_agent_loop(user_message, user_id, max_steps=4):
    # Retrieve: ground the conversation before the first Plan step.
    context_block, sources, rag_error = _get_rag_context(user_message)
    trace = [{"step": "retrieve", "type": "rag", "sources": sources, "error": rag_error}]

    # Prefetch: give the model the user's real budgets up front (via MCP) so it
    # never has to decide to call a tool - small models often skip tool calls.
    overview, overview_via = get_budget_overview(user_id)
    trace.append({"step": "prefetch", "type": "tool_call", "tool": "get_budget_overview",
                  "args": {"status": "active"}, "via": overview_via})

    system_prompt = (
        SYSTEM_PROMPT
        + "\n\nThe user's active budgets (live data):\n" + _format_overview(overview)
        + "\n\nKnowledge base excerpts:\n" + (context_block or "(none available)")
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for step in range(max_steps):
        # Plan: the LLM decides whether to call a tool or answer.
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "tools": TOOLS, "stream": False},
            timeout=60,
        )
        response.raise_for_status()
        message = response.json()["message"]
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            trace.append({"step": step, "type": "final_answer"})
            return {"answer": message.get("content", ""), "sources": sources, "trace": trace}

        for call in tool_calls:
            fn_name = call["function"]["name"]
            fn_args = call["function"].get("arguments") or {}
            if isinstance(fn_args, str):
                fn_args = json.loads(fn_args or "{}")

            # Act
            result, source = _call_tool(fn_name, fn_args, user_id)
            trace.append({"step": step, "type": "tool_call", "tool": fn_name, "args": fn_args, "via": source})

            # Observe -> Adapt happens on the next Plan step with this result in context.
            messages.append({"role": "tool", "content": json.dumps(result)})

    return {
        "answer": "I wasn't able to finish reasoning about that in time — try a more specific question.",
        "sources": sources,
        "trace": trace,
    }