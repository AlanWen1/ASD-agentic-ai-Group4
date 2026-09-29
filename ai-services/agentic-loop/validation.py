import asyncio
import os
import socket
import subprocess
import sys
import textwrap
import json
import time
from urllib.parse import urlparse

import requests

EXPECTED_TOOLS = {
    "get_expenses", "get_categories", "get_bills", "get_bills_summary",
    "get_income_sources", "get_pay_schedules", "get_savings_goals", "get_budgets"
}


def _host_port(url):
    parsed = urlparse(url)
    return parsed.hostname or "localhost", parsed.port or 80


def _port_open(url):
    host, port = _host_port(url)
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _start_local_mcp(repo_root, url):
    """Start the existing MCP server locally when it is not already listening."""
    if _port_open(url):
        return None, False

    server_dir = repo_root / "ai-services" / "mcp-server"
    server_file = server_dir / "server.py"
    if not server_file.is_file():
        return None, False

    env = os.environ.copy()
    env.setdefault("PORT", str(_host_port(url)[1]))
    try:
        process = subprocess.Popen(
            [sys.executable, str(server_file)],
            cwd=str(server_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except OSError:
        return None, False

    deadline = time.time() + 12
    while time.time() < deadline:
        if _port_open(url):
            return process, True
        if process.poll() is not None:
            return process, True
        time.sleep(0.25)
    return process, True


async def validate_mcp(url=None, user_id=None, repo_root=None):
    url = url or os.environ.get("MCP_SERVER_URL", "http://localhost:5100/mcp")
    user_id = user_id or int(os.environ.get("VALIDATION_USER_ID", "1"))
    out = {
        "connected": False,
        "auto_started": False,
        "tools": [],
        "calls": [],
        "errors": [],
    }

    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:
        out["errors"].append(
            "MCP SDK unavailable in the agentic-loop environment: " + str(exc)
        )
        return out

    process = None
    if repo_root is not None:
        process, out["auto_started"] = _start_local_mcp(repo_root, url)

    expected_args = {name: {"user_id": user_id} for name in EXPECTED_TOOLS}
    try:
        async with streamable_http_client(url) as streams:
            rs, ws = streams[0], streams[1]
            async with ClientSession(rs, ws) as session:
                info = await session.initialize()
                out["connected"] = True
                out["server"] = getattr(
                    getattr(info, "server_info", None), "name", "unknown"
                )
                listed = await session.list_tools()
                out["tools"] = [tool.name for tool in listed.tools]
                out["missing_tools"] = sorted(EXPECTED_TOOLS - set(out["tools"]))
                out["unexpected_tools"] = sorted(set(out["tools"]) - EXPECTED_TOOLS)

                for name in sorted(EXPECTED_TOOLS & set(out["tools"])):
                    try:
                        result = await session.call_tool(name, expected_args[name])
                        blocks = [
                            block.text
                            for block in result.content
                            if hasattr(block, "text")
                        ]
                        out["calls"].append({
                            "tool": name,
                            "protocol_error": bool(getattr(result, "isError", False)),
                            "response": "\n".join(blocks)[:700],
                        })
                    except Exception as exc:
                        out["calls"].append({
                            "tool": name,
                            "protocol_error": True,
                            "response": f"{type(exc).__name__}: {exc}",
                        })
    except Exception as exc:
        if not _port_open(url):
            out["errors"].append(
                f"MCP server is not reachable at {url}. "
                f"Start ai-services/mcp-server/server.py first. "
                f"Underlying error: {type(exc).__name__}: {exc}"
            )
        else:
            out["errors"].append(
                f"MCP session failed at {url}: {type(exc).__name__}: {exc}"
            )
    finally:
        if process is not None and out["auto_started"] and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    return out


def validate_rag(url=None):
    url = url or os.environ.get("RAG_SERVER_URL", "http://localhost:5101")
    base = url.rstrip("/")
    out = {"health": None, "refresh": None, "retrieval": [], "generation": None, "errors": []}

    try:
        r = requests.get(base + "/health", timeout=10)
        out["health"] = r.json()
        r.raise_for_status()
    except (requests.RequestException, ValueError) as exc:
        out["errors"].append(f"health: {exc}")
        return out

    try:
        r = requests.post(base + "/refresh_corpus", timeout=20)
        out["refresh"] = r.json()
        r.raise_for_status()
    except (requests.RequestException, ValueError) as exc:
        out["errors"].append(f"refresh_corpus: {exc}")

    for query in (
        "how do I set a budget",
        "what does an overdue bill mean",
        "how do I add an expense",
    ):
        try:
            r = requests.post(
                base + "/retrieve_context",
                json={"query": query, "k": 3},
                timeout=20,
            )
            body = r.json()
            r.raise_for_status()
            out["retrieval"].append({"query": query, "results": body.get("results", [])})
        except (requests.RequestException, ValueError) as exc:
            out["retrieval"].append({"query": query, "error": str(exc)})

    try:
        r = requests.post(
            base + "/answer_question",
            json={"query": "What does an overdue bill mean?", "k": 3},
            timeout=120,
        )
        out["generation"] = r.json()
    except (requests.RequestException, ValueError) as exc:
        out["errors"].append(f"answer_question: {exc}")

    return out


def print_validation(mode, data):
    print("\n" + "=" * 70)
    print(mode.upper() + " VALIDATION")
    print("=" * 70)

    if mode == "mcp":
        print("[{}] MCP connection".format(
            "PASS" if data.get("connected") else "FAIL"
        ))
        if data.get("auto_started"):
            print("[INFO] MCP server was started locally for validation.")
        if data.get("server"):
            print("[INFO] Server:", data["server"])

        ok = (
            len(data.get("tools", [])) == 8
            and not data.get("missing_tools")
            and not data.get("unexpected_tools")
        )
        print("[{}] Tool discovery: {}/8".format(
            "PASS" if ok else "WARN",
            len(data.get("tools", [])),
        ))

        if data.get("missing_tools"):
            print("[WARN] Missing tools:", ", ".join(data["missing_tools"]))
        if data.get("unexpected_tools"):
            print("[WARN] Unexpected tools:", ", ".join(data["unexpected_tools"]))

        for call in data.get("calls", []):
            state = "FAIL" if call["protocol_error"] else "PASS"
            print(f"  [{state}] {call['tool']}")
            response = str(call.get("response", "")).strip()
            if not response:
                print("      (empty response)")
            else:
                try:
                    parsed = json.loads(response)
                    if isinstance(parsed, dict):
                        print("      JSON object: " + ", ".join(str(k) for k in parsed.keys()))
                    elif isinstance(parsed, list):
                        print(f"      JSON array: {len(parsed)} item(s)")
                    else:
                        for line in textwrap.wrap(str(parsed), width=82):
                            print("      " + line)
                except (TypeError, ValueError):
                    for line in textwrap.wrap(" ".join(response.split()), width=82):
                        print("      " + line)
        for error in data.get("errors", []):
            print("[FAIL] " + error)

    else:
        h = data.get("health") or {}
        print("[{}] RAG health: loaded={} chunks={}".format(
            "PASS" if h.get("service") == "rag-server" else "WARN",
            h.get("corpus_loaded"),
            h.get("chunk_count"),
        ))
        refresh = data.get("refresh") or {}
        print("[{}] Corpus refresh".format(
            "PASS" if refresh.get("status") == "success" else "WARN"
        ))
        for item in data.get("retrieval", []):
            top = (item.get("results") or [{}])[0]
            print("[{}] Retrieval: {} -> {} distance={}".format(
                "PASS" if top else "FAIL",
                item["query"],
                top.get("source_id"),
                top.get("distance"),
            ))
        gen = data.get("generation") or {}
        if "answer" in gen:
            print("[PASS] Grounded generation")
            print("  Confidence:", str(gen.get("confidence_category", "unknown")).upper())
            print("  Citations:", ", ".join(map(str, gen.get("citations") or [])) or "(none)")
            print("  Answer:")
            for line in textwrap.wrap(str(gen.get("answer", "")).strip(), width=82):
                print("    " + line)
        elif gen:
            print("[WARN] Grounded generation: " + str(gen))
        for error in data.get("errors", []):
            print("[WARN] " + error)