import ast
import json
import re
import sqlite3
import subprocess
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build"}

def repo_files(root):
    try:
        names = subprocess.run(["git", "-C", str(root), "ls-files"], check=True, capture_output=True, text=True, timeout=15).stdout.splitlines()
        return [root / p for p in names if (root / p).is_file()]
    except (OSError, subprocess.SubprocessError):
        return [p for p in root.rglob("*") if p.is_file() and not any(x in p.parts for x in SKIP_DIRS)]

def read(root, relative_path, limit=7000):
    p = (root / relative_path).resolve()
    p.relative_to(root)
    if not p.is_file():
        return ""
    text = p.read_text(encoding="utf-8")
    return text if len(text) <= limit else text[:limit] + "\n...truncated..."

def syntax_check(root):
    failures = []
    checked = 0
    for p in repo_files(root):
        if p.suffix != ".py":
            continue
        checked += 1
        try:
            ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except (SyntaxError, UnicodeDecodeError) as exc:
            failures.append({"file": p.relative_to(root).as_posix(), "error": str(exc)})
    return {"checked": checked, "failures": failures}

def database_check(root):
    dbs, schemas = [], []
    for p in repo_files(root):
        rel = p.relative_to(root).as_posix()
        if p.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            try:
                con = sqlite3.connect(p)
                tables = [x[0] for x in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
                con.close()
                dbs.append({"file": rel, "tables": tables})
            except sqlite3.Error as exc:
                dbs.append({"file": rel, "error": str(exc)})
        elif p.name in {"schema.sql", "seed.sql"}:
            schemas.append(rel)
    return {"database_dirs": sorted({p.relative_to(root).as_posix() for p in root.rglob("database") if p.is_dir()}), "sqlite": dbs, "schema_seed": schemas}

def compose_check(root):
    result = {}
    for p in repo_files(root):
        if p.name == "docker-compose.yml" or p.name.startswith("docker-compose."):
            text = read(root, p.relative_to(root).as_posix(), 30000)
            result[p.relative_to(root).as_posix()] = sorted(set(re.findall(r"^  ([A-Za-z0-9_.-]+):\s*$", text, re.M)))
    return {"services": result, "dockerfiles": [p.relative_to(root).as_posix() for p in repo_files(root) if p.name.lower() == "dockerfile"]}

def devops_check(root):
    result = {}
    for p in repo_files(root):
        rel = p.relative_to(root).as_posix()
        if rel.startswith(".github/workflows/"):
            text = read(root, rel, 30000)
            result[rel] = {
                "jobs": re.findall(r"^  ([A-Za-z0-9_.-]+):\s*$", text, re.M),
                "python_tests": bool(re.search(r"pytest|unittest", text, re.I)),
                "node_tests": bool(re.search(r"npm\s+(test|run test)|yarn test|pnpm test", text, re.I)),
                "docker_build": "docker build" in text.lower()
            }
    return result

def candidates(root, mode):
    paths = [p.relative_to(root).as_posix() for p in repo_files(root)]
    if mode == "database":
        paths = [p for p in paths if "/database/" in "/" + p or p.endswith(("/schema.sql", "/seed.sql"))]
    elif mode == "implementation":
        paths = [p for p in paths if p.endswith((".py", ".js", ".ts", ".tsx", ".jsx"))]
    elif mode == "microservices":
        paths = [p for p in paths if p.startswith(("ai-services/", "docs/architecture/")) or "docker-compose" in p or p.endswith("/Dockerfile")]
    elif mode == "devops":
        paths = [p for p in paths if p.startswith(".github/workflows/") or "docker-compose" in p or p.endswith("/Dockerfile")]
    elif mode == "mcp":
        paths = [p for p in paths if p.startswith("ai-services/mcp-server/") or p.endswith("/mcp_client.py")]
    elif mode == "rag":
        paths = [p for p in paths if p.startswith("ai-services/rag-server/") or p.endswith("/app.py")]
    return sorted(set(paths), key=lambda p: (len(p), p))[:80]

def static_evidence(root, mode):
    out = {"python_syntax": syntax_check(root)}
    if mode == "database":
        out["database"] = database_check(root)
    elif mode == "microservices":
        out["architecture"] = compose_check(root)
    elif mode == "devops":
        out["devops"] = devops_check(root)
    elif mode == "mcp":
        out["mcp"] = {
            "server": read(root, "ai-services/mcp-server/server.py", 9000),
            "tools": read(root, "ai-services/mcp-server/tools.py", 9000),
            "client_count": len([p for p in repo_files(root) if p.name == "mcp_client.py"])
        }
    elif mode == "rag":
        corpus = root / "ai-services/rag-server/corpus/corpus.jsonl"
        rows, bad = [], []
        if corpus.exists():
            for n, line in enumerate(corpus.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        bad.append({"line": n, "error": str(exc)})
        out["rag"] = {
            "corpus_exists": corpus.is_file(),
            "records": len(rows),
            "unique_ids": len({x.get("id") for x in rows}) == len(rows),
            "bad_records": bad,
            "pipeline": read(root, "ai-services/rag-server/rag_pipeline.py", 11000)
        }
    return out