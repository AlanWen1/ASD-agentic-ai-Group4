"""
Shared MCP client helper — Release 1 requirement.

This exact file is copied into each of the five backends below
(expense-category-tracker, student-1-budget, student-3, student-5,
bill-tracker) rather than imported from one shared package, because each
backend is deployed as its own separate service/container — the same
reason each backend already keeps its own agent.py/ai_service.py instead
of sharing one Python module across services.

Wraps the official `mcp` Python SDK's async Streamable HTTP client
session (initialize -> call_tool) behind one blocking function, so a
synchronous Flask route can call the shared MCP server
(../../ai-services/mcp-server/) with a single function call.
"""
import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://host.docker.internal:5100/mcp")


async def _call_tool_async(tool_name, arguments):
    async with streamable_http_client(MCP_SERVER_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await session.call_tool(tool_name, arguments)


def call_mcp_tool(tool_name, **arguments):
    """Call `tool_name` on the shared MCP server with `arguments` and
    return its result as plain Python data (usually a dict). On any
    failure — the MCP server unreachable, or the tool itself reporting
    an error — returns a structured {"error": "..."} dict rather than
    raising, matching the convention the MCP server's own tools.py
    already uses.
    """
    try:
        result = asyncio.run(_call_tool_async(tool_name, arguments))
    except Exception as exc:
        return {"error": f"Could not reach MCP server at {MCP_SERVER_URL}: {exc}"}

    if not result.content:
        return {"error": "Empty result from MCP server"}

    text = result.content[0].text
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return {"error": f"Could not parse MCP server response: {text[:200]}"}
