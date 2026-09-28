import argparse
import json
import os
import textwrap
from pathlib import Path

import requests

from llm import ask, health, parse_json
from repository_checks import candidates, static_evidence, read
from validation import validate_mcp, validate_rag, print_validation

LABELS = {
    "database": "Database review",
    "implementation": "Implementation review",
    "microservices": "Microservices architecture review",
    "devops": "DevOps pipeline review",
    "mcp": "MCP validation",
    "rag": "RAG validation",
}

GOALS = {
    "database": "Review schemas, SQLite data, ownership/isolation, APIs, integrity and security.",
    "implementation": "Review backend/frontend correctness, integration, errors, auth, tests and AI use.",
    "microservices": "Review service boundaries, API flow, database ownership, AI services, networking and configuration.",
    "devops": "Review GitHub Actions, tests, builds, Docker, environment assumptions and CI coverage.",
    "mcp": "Validate the real MCP server, eight tools, backend clients, user scoping and Streamable HTTP.",
    "rag": "Validate corpus, retrieval, grounded generation, citations, confidence and REST integration.",
}

def _wrap(value, width=92):
    text = str(value if value is not None else "").replace("\r", "").strip()
    if not text:
        return ["(none)"]
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        lines.extend(textwrap.wrap(raw, width=width) or [""])
    return lines or ["(none)"]

def _print_block(label, value, indent="  ", width=92):
    print(f"{indent}{label}:")
    for line in _wrap(value, width):
        print(f"{indent}  {line}")

def _print_header(title, char="="):
    print("\n" + char * 70)
    print(title)
    print(char * 70)

def safe_llm(ollama_url, model, system, prompt):
    try:
        return parse_json(
            ask(system, prompt, url=ollama_url, model=model)
        ), None
    except requests.HTTPError as exc:
        body = ""
        try:
            body = exc.response.text[:1500] if exc.response is not None else ""
        except Exception:
            pass
        return {}, f"Ollama HTTP error: {exc}. {body}".strip()
    except requests.RequestException as exc:
        return {}, f"Ollama request failed: {exc}"
    except Exception as exc:
        return {}, f"LLM stage failed: {type(exc).__name__}: {exc}"

def _static_check_summary(evidence):
    syntax = evidence.get("python_syntax", {})
    checked = syntax.get("checked", 0)
    failures = syntax.get("failures", [])
    print("STATIC CHECKS")
    state = "PASS" if not failures else "WARN"
    print(f"  [{state}] Python syntax: {checked} file(s) checked, {len(failures)} failure(s)")
    if failures:
        for item in failures[:5]:
            print(f"      {item.get('file')}: {item.get('error')}")
        if len(failures) > 5:
            print(f"      ... and {len(failures) - 5} more")

def _print_findings(findings):
    if not findings:
        print("  No structured findings returned.")
        return
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    ordered = sorted(
        findings.values(),
        key=lambda x: order.get(str(x.get("severity", "info")).lower(), 5),
    )
    for number, item in enumerate(ordered, 1):
        severity = str(item.get("severity", "info")).upper()
        print(f"\n  {number}. [{severity}] {item.get('title', '(untitled)')}")
        print(f"     File: {item.get('file', '(not specified)')}")
        _print_block("Evidence", item.get("evidence", "(none)"), indent="     ")
        _print_block("Recommendation", item.get("recommendation", "(none)"), indent="     ")

def review_mode(root, mode, model, ollama_url, iterations):
    if mode in {"mcp", "rag"}:
        _print_header(LABELS[mode].upper())
        if mode == "mcp":
            import asyncio
            live = asyncio.run(validate_mcp(repo_root=root))
        else:
            live = validate_rag()
        print_validation(mode, live)
        return 0

    _print_header(LABELS[mode].upper())
    print(f"MODEL: {model}")
    evidence = static_evidence(root, mode)
    _static_check_summary(evidence)

    pool = candidates(root, mode)
    planner, llm_error = safe_llm(
        ollama_url,
        model,
        "You are the planning agent for a software audit. Return ONLY JSON. "
        "Choose 3-8 paths from candidate_files. Never invent paths.",
        f"Mode: {mode}\nGoal: {GOALS[mode]}\n"
        f"candidate_files={json.dumps(pool)}\n"
        f"evidence={json.dumps(evidence, default=str)[:13000]}\n"
        '{"focus_paths":["path"],"checks":["check"],"reasoning":"brief"}'
    )
    if llm_error:
        print(f"[WARN] LLM planning skipped: {llm_error}")

    paths = [
        p for p in planner.get("focus_paths", [])
        if isinstance(p, str) and (root / p).is_file()
    ]
    paths = list(dict.fromkeys(paths))
    if not paths:
        paths = pool[:10]
        print("PLAN SOURCE: deterministic candidate selection")
    else:
        print("PLAN SOURCE: LLM-selected paths")

    findings = {}
    summary = ""

    for iteration in range(1, max(1, iterations) + 1):
        print(f"\nITERATION {iteration}/{max(1, iterations)}")
        print("PLAN")
        for number, path in enumerate(paths[:10], 1):
            print(f"  {number}. {path}")

        file_text = "\n\n".join(
            f"FILE: {p}\n{read(root, p)}" for p in paths[:10]
        )
        result, review_error = safe_llm(
            ollama_url,
            model,
            "You are the review agent for a software audit. Return ONLY JSON. "
            "Use supplied evidence only. Every finding needs severity,title,file,evidence,recommendation.",
            f"Mode: {mode}\nGoal: {GOALS[mode]}\nIteration: {iteration}\n"
            f"Evidence={json.dumps(evidence, default=str)[:15000]}\n"
            f"Files:\n{file_text[:42000]}\n"
            '{"summary":"...","confidence":"high|medium|low",'
            '"findings":[{"severity":"critical|high|medium|low|info","title":"...",'
            '"file":"path","evidence":"...","recommendation":"..."}],'
            '"follow_up_paths":["path"]}'
        )
        if review_error:
            result = {
                "summary": "LLM review was unavailable. Deterministic repository checks were completed.",
                "confidence": "low",
                "findings": [],
                "follow_up_paths": [],
            }
            print(f"[WARN] LLM review skipped: {review_error}") 
            print("[INFO] Continuing with deterministic repository checks.")

        summary = str(result.get("summary", summary)).strip()
        print("OBSERVE / REVIEW")
        _print_block("Summary", summary or "(no summary)", indent="  ")
        print(f"  Confidence: {str(result.get('confidence', 'low')).upper()}")

        iteration_findings = result.get("findings", [])
        valid_iteration_findings = 0
        for item in iteration_findings if isinstance(iteration_findings, list) else []:
            if isinstance(item, dict):
                key = (
                    str(item.get("title", "")).lower(),
                    str(item.get("file", "")),
                )
                findings[key] = item
                valid_iteration_findings += 1
        print(f"  Findings this iteration: {valid_iteration_findings}")

        followups = [
            p for p in result.get("follow_up_paths", [])
            if isinstance(p, str) and (root / p).is_file()
        ]
        followups = list(dict.fromkeys(followups))
        if not followups or iteration == max(1, iterations):
            if followups and iteration == max(1, iterations):
                print("  Follow-up paths available, but maximum iterations reached.")
            break
        paths = followups
        print("FOLLOW-UP")
        for number, path in enumerate(paths[:10], 1):
            print(f"  {number}. {path}")

    _print_header("FINAL RESULT", char="-")
    _print_block("Summary", summary or "No summary produced.", indent="")
    print(f"Confidence: {str(result.get('confidence', 'low')).upper()}")
    print("\nFINDINGS")
    _print_findings(findings)
    return len(findings)

def choose_mode():
    print("\nLOCAL AGENTIC REVIEWER")
    print("Primary model: llama3.1:8b")
    print("  1. Database review")
    print("  2. Implementation review")
    print("  3. Microservices architecture review")
    print("  4. DevOps pipeline review")
    print("  5. MCP validation")
    print("  6. RAG validation")
    print("  7. All reviews + MCP/RAG validation")
    print("  0. Exit")
    while True:
        value = input("Selection: ").strip()
        if value == "0":
            raise SystemExit(0)
        if value == "7":
            return list(LABELS)
        try:
            index = int(value) - 1
            if 0 <= index < len(LABELS):
                return [list(LABELS)[index]]
        except ValueError:
            pass
        print("Choose 0-7.")

def main():
    parser = argparse.ArgumentParser(description="Local llama3.1:8b agentic repository reviewer")
    parser.add_argument("--repo")
    parser.add_argument("--mode", choices=list(LABELS) + ["all"])
    parser.add_argument("--model", default=os.environ.get("AGENT_MODEL", "llama3.1:8b"))
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--max-iterations", type=int, default=int(os.environ.get("AGENT_MAX_ITERATIONS", "3")))
    args = parser.parse_args()

    root = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[2]
    ok, names = health(args.ollama_url, args.model)
    if ok:
        print(f"[PASS] Ollama model listed: {args.model} at {args.ollama_url}")
    else:
        print(f"[WARN] Ollama model is not available to the reviewer: {args.model}")
        print("Available:", ", ".join(names) if names else "(none)")
        print("Review modes will still run deterministic checks; LLM stages may fall back or be skipped.")

    if args.mode == "all":
        selected = list(LABELS)
    elif args.mode:
        selected = [args.mode]
    else:
        selected = choose_mode()

    total = 0
    review_count = 0
    validation_count = 0

    for mode in selected:
        try:
            result = review_mode(
                root,
                mode,
                args.model,
                args.ollama_url,
                max(1, args.max_iterations),
            )
            if mode in {"mcp", "rag"}:
                validation_count += 1
            else:
                review_count += 1
                total += result
        except KeyboardInterrupt:
            print("\nInterrupted.")
            return 130
        except Exception as exc:
            print(f"[FAIL] {mode}: {type(exc).__name__}: {exc}")

    print(
        f"\nSESSION COMPLETE: {review_count} review mode(s), "
        f"{validation_count} validation mode(s), {total} finding(s)"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())