"""Temporary native HTTP stack for environments without Docker.

This validates cross-service business behavior; it does not claim to be the
required Docker local deployment. All databases and server logs are temporary.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULES = {"finance": "finance-application", "budget": "student-1-budget", "expense": "expense-category-tracker",
           "income": "student-3", "bill": "bill-tracker", "savings": "student-5"}


def main(output):
    processes, logs = [], []
    with tempfile.TemporaryDirectory(prefix="release2-http-") as directory:
        temp = Path(directory)
        try:
            for offset, (name, module) in enumerate(MODULES.items()):
                common = {**os.environ, "AI_ENABLED": "false", "MCP_ENABLED": "false", "RAG_ENABLED": "false",
                    "MULTI_AGENT_ENABLED": "false", "APP_ENV": "local", "DATABASE_PATH": str(temp / (name + ".db")),
                    "AUTH_DATABASE_URL": "http://localhost:6000", "BILL_DATABASE_URL": "http://localhost:6004"}
                for m, port in zip(MODULES, range(3000, 3006)):
                    common[m.upper() + "_FRONTEND_URL"] = f"http://localhost:{port}"
                for role, port in (("database", 6000 + offset), ("backend", 5000 + offset), ("frontend", 3000 + offset)):
                    with socket.socket() as probe:
                        if probe.connect_ex(("127.0.0.1", port)) == 0:
                            raise RuntimeError(f"Port {port} is already in use; refusing to disturb another stack")
                    env = {**common, "DATABASE_URL": f"http://localhost:{6000 + offset}",
                        "DATABASE_SERVICE_URL": f"http://localhost:{6000 + offset}", "DATABASE_API_URL": f"http://localhost:{6000 + offset}",
                        "BACKEND_URL": f"http://localhost:{5000 + offset}", "BACKEND_SERVICE_URL": f"http://localhost:{5000 + offset}",
                        "BACKEND_API_URL": f"http://localhost:{5000 + offset}"}
                    folder = ROOT / module / role
                    entry = "server.py" if name == "budget" and role == "frontend" else "app.py"
                    log = (temp / (name + "-" + role + ".log")).open("w+")
                    logs.append(log)
                    processes.append((name + "-" + role, subprocess.Popen([sys.executable, entry], cwd=folder,
                        env=env, stdout=log, stderr=subprocess.STDOUT)))
            deadline = time.monotonic() + 35
            for port in range(3000, 3006):
                while time.monotonic() < deadline:
                    with socket.socket() as probe:
                        if probe.connect_ex(("127.0.0.1", port)) == 0:
                            break
                    failed = [name for name, process in processes if process.poll() is not None]
                    if failed:
                        raise RuntimeError("Services exited: " + ", ".join(failed))
                    time.sleep(0.2)
                else:
                    raise RuntimeError(f"Frontend {port} did not start")
            deployment = temp / "deployment.json"
            deployment.write_text(json.dumps({"profile": "baseline", "environment": "native", "frontends": {
                name: f"http://localhost:{3000 + offset}" for offset, name in enumerate(MODULES)}}))
            result = subprocess.run([sys.executable, str(ROOT / "scripts/deploy/cloud_smoke.py"),
                "--deployment", str(deployment), "--output", str(Path(output).resolve())], check=False)
            if result.returncode:
                # Only show the last server error lines. Session tokens are redacted.
                import re
                for (name, _), log in zip(processes, logs):
                    log.seek(0)
                    lines = [line for line in log.read().splitlines() if "Traceback" in line or "Error" in line or "Exception" in line]
                    for line in lines[-4:]:
                        print(name + ": " + re.sub(r"/sessions/[^\s]+", "/sessions/[redacted]", line))
            return result.returncode
        finally:
            for _, process in processes:
                process.terminate()
            for _, process in processes:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            for log in logs:
                log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="docs/release-2/evidence/native/application-tests.json")
    raise SystemExit(main(parser.parse_args().output))
