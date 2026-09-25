"""
Terminal-based MCP client test — real MCP protocol, not a raw HTTP call.

This is the "Terminal B" verification the Release 1 evidence log asks
for: it speaks the actual Model Context Protocol (initialize a session,
list tools, call a tool) against the running server, using the official
`mcp` SDK's client, rather than just calling tools.py's Python functions
directly (that's what `python3 tools.py` already does, and only proves
the underlying HTTP forwarding works — it doesn't prove the MCP layer
itself is wired up correctly).

Usage:
    # Terminal A:
    ./run_local.sh

    # Terminal B:
    python3 client_test.py [user_id]
"""
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SERVER_URL = "http://localhost:5100/mcp"


async def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    async with streamable_http_client(SERVER_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            print(f"Connected to: {init_result.server_info.name}")

            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"Tools available ({len(tool_names)}): {tool_names}")

            print(f"\nCalling get_categories(user_id={user_id}) ...")
            result = await session.call_tool("get_categories", {"user_id": user_id})
            for block in result.content:
                if hasattr(block, "text"):
                    print(block.text)

            print(f"\nCalling get_bills_summary(user_id={user_id}) ...")
            result = await session.call_tool("get_bills_summary", {"user_id": user_id})
            for block in result.content:
                if hasattr(block, "text"):
                    print(block.text)


if __name__ == "__main__":
    asyncio.run(main())
