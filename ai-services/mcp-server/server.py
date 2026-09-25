"""
MCP server — Release 1 requirement.

Shared, non-containerised Model Context Protocol server exposing
read-only tools over the team's five real Database APIs (see tools.py's
module docstring for exactly which endpoint each tool forwards to and
why). Every backend accesses these tools through its own backend/API,
which acts as an MCP client (see each module's own mcp_client.py /
routes once wired in) — the MCP server itself never talks to a frontend
directly.

Uses the official `mcp` Python SDK (2.x: MCPServer, formerly FastMCP in
1.x — see requirements.txt) over Streamable HTTP, so any standard MCP
client can call it, not just this team's own backends.

Run this as a local host process (NOT a docker-compose service — Release
1 requires AI-Mode, the MCP server, the RAG server, and the agentic loop
to all be non-containerised):

    ./run_local.sh

or directly:

    python3 server.py

It listens on http://localhost:5100/mcp by default (override with PORT).
Start it BEFORE `docker compose up`, same as ai-mode (see
../ai-mode/README.md) — the five backends will reach it at
http://host.docker.internal:5100 once wired in.
"""
import os

from mcp.server.mcpserver import MCPServer

from tools import (
    get_bills,
    get_bills_summary,
    get_budgets,
    get_categories,
    get_expenses,
    get_income_sources,
    get_pay_schedules,
    get_savings_goals,
)

mcp = MCPServer("Personal Finance MCP Server")

AVAILABLE_TOOLS = [
    "get_expenses",
    "get_categories",
    "get_bills",
    "get_bills_summary",
    "get_income_sources",
    "get_pay_schedules",
    "get_savings_goals",
    "get_budgets",
]


@mcp.tool(name="get_expenses")
def get_expenses_tool(user_id: int, category_id: int | None = None):
    """List a user's expenses (Expense & Category Manager), optionally filtered by category_id."""
    return get_expenses(user_id, category_id)


@mcp.tool(name="get_categories")
def get_categories_tool(user_id: int):
    """List a user's expense categories (Expense & Category Manager)."""
    return get_categories(user_id)


@mcp.tool(name="get_bills")
def get_bills_tool(user_id: int):
    """List a user's bills (Bill Manager)."""
    return get_bills(user_id)


@mcp.tool(name="get_bills_summary")
def get_bills_summary_tool(user_id: int):
    """Total/pending bill amounts and overdue count for a user (Bill Manager)."""
    return get_bills_summary(user_id)


@mcp.tool(name="get_income_sources")
def get_income_sources_tool(user_id: int):
    """List a user's income sources (Income & Pay Schedule Manager)."""
    return get_income_sources(user_id)


@mcp.tool(name="get_pay_schedules")
def get_pay_schedules_tool(user_id: int):
    """List a user's pay schedules (Income & Pay Schedule Manager)."""
    return get_pay_schedules(user_id)


@mcp.tool(name="get_savings_goals")
def get_savings_goals_tool(user_id: int | None = None):
    """List savings goals (Savings Goal Manager). Note: the underlying
    endpoint does not currently filter by user; see tools.py docstring."""
    return get_savings_goals(user_id)


@mcp.tool(name="get_budgets")
def get_budgets_tool(user_id: int):
    """List a user's budgets (Budget Manager)."""
    return get_budgets(user_id)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5100))
    print("Starting Personal Finance MCP Server...")
    print("Server status: RUNNING")
    print(f"Listening on http://0.0.0.0:{port}/mcp (Streamable HTTP)")
    print("Available tools:")
    for tool in AVAILABLE_TOOLS:
        print(f"- {tool}")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
