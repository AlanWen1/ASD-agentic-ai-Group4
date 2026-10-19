import argparse
import json
import os
import textwrap
from pathlib import Path

import requests

from llm import ask, health, parse_json
from repository_checks import candidates, static_evidence, read
from validation import validate_mcp, validate_rag, validate_multi_agent, print_validation

LABELS = {
    "database": "Database review",
    "implementation": "Implementation review",
    "microservices": "Microservices architecture review",
    "devops": "DevOps pipeline review",
    "mcp": "MCP validation",
    "rag": "RAG validation",
    "multi_agent": "Multi-Agent workflow validation",
    "testing": "Testing report review (pre-commit + post-commit evidence)",
    "deployment": "Cloud deployment report review",
}

GOALS = {
    "database": "Review schemas, SQLite data, ownership/isolation, APIs, integrity and security.",
    "implementation": "Review backend/frontend correctness, integration, errors, auth, tests and AI use.",
    "microservices": "Review service boundaries, API flow, database ownership, AI services, networking and configuration.",
    "devops": "Review GitHub Actions, tests, builds, Docker, environment assumptions and CI coverage.",
    "mcp": "Validate the real MCP server, registered tools, user scoping and Streamable HTTP.",
    "rag": "Validate corpus, retrieval, grounded generation, citations, confidence and REST integration.",
    "multi_agent": "Validate the shared Multi-Agent Server: health, then a live Planner/Worker/Reviewer run that stops at human review.",
    "testing": "Review pre-commit security scan evidence and post-commit CI/CD endpoint test evidence against the Release 2 requirements.",
    "deployment": "Review cloud deployment scripts, the cloud-deployment.yml workflow, and deployment evidence against the Release 2 requirements.",
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
        parsed = parse_json(
            ask(system, prompt, url=ollama_url, model=model)
        )
        if not parsed:
            return {}, "LLM returned no usable JSON."
        return parsed, None
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

def _deterministic_review(mode, evidence, pool):
    syntax = evidence.get("python_syntax", {})
    failures = syntax.get("failures", [])
    findings = []

    if failures:
        for item in failures[:5]:
            findings.append({
                "severity": "high",
                "title": "Python syntax error detected",
                "file": item.get("file", "(unknown)"),
                "evidence": item.get("error", "Python parser reported an error."),
                "recommendation": "Fix the syntax error and rerun the review.",
            })
    else:
        findings.append({
            "severity": "info",
            "title": "Python syntax checks passed",
            "file": "repository-wide",
            "evidence": f"{syntax.get('checked', 0)} Python file(s) were parsed successfully.",
            "recommendation": "Keep repository-wide syntax validation in the review pipeline.",
        })

    if mode == "database":
        db = evidence.get("database", {})
        sqlite_files = db.get("sqlite", [])
        broken = [x for x in sqlite_files if x.get("error")]
        if broken:
            for item in broken[:5]:
                findings.append({
                    "severity": "high",
                    "title": "SQLite database could not be inspected",
                    "file": item.get("file", "(unknown)"),
                    "evidence": item.get("error"),
                    "recommendation": "Validate or repair the database file before relying on it.",
                })
        elif sqlite_files or db.get("schema_seed"):
            findings.append({
                "severity": "info",
                "title": "Database artefacts discovered",
                "file": "repository",
                "evidence": f"{len(sqlite_files)} SQLite file(s) and {len(db.get('schema_seed', []))} schema/seed file(s) found.",
                "recommendation": "Continue checking ownership, user isolation and API access.",
            })
        else:
            findings.append({
                "severity": "medium",
                "title": "No database artefacts discovered",
                "file": "repository",
                "evidence": "No SQLite files or schema.sql/seed.sql files were found.",
                "recommendation": "Confirm where database definitions are stored.",
            })

    elif mode == "microservices":
        arch = evidence.get("architecture", {})
        services = arch.get("services", {})
        count = sum(len(v) for v in services.values())
        findings.append({
            "severity": "info" if count else "medium",
            "title": "Compose service definitions",
            "file": "docker-compose files",
            "evidence": f"{count} service definition(s) detected.",
            "recommendation": "Verify each service has clear ownership, networking and API boundaries.",
        })

    elif mode == "devops":
        workflows = evidence.get("devops", {})
        if workflows:
            for path, info in workflows.items():
                checks = []
                if info.get("python_tests"):
                    checks.append("Python tests")
                if info.get("node_tests"):
                    checks.append("Node tests")
                if info.get("docker_build"):
                    checks.append("Docker build")
                findings.append({
                    "severity": "info" if checks else "low",
                    "title": "CI workflow coverage",
                    "file": path,
                    "evidence": ", ".join(checks) if checks else "No recognised test/build markers.",
                    "recommendation": "Ensure required test and build checks are enforced in CI.",
                })
        else:
            findings.append({
                "severity": "medium",
                "title": "No GitHub Actions workflows discovered",
                "file": ".github/workflows",
                "evidence": "No workflow files were found.",
                "recommendation": "Add or verify CI workflows for required checks.",
            })

    elif mode == "implementation":
        findings.append({
            "severity": "info",
            "title": "Implementation review fallback",
            "file": "repository",
            "evidence": f"{len(pool)} implementation candidate file(s) were selected after the LLM stage was unavailable.",
            "recommendation": "Run again with a working local model for deeper behavioural analysis.",
        })

    elif mode == "testing":
        testing = evidence.get("testing", {})
        pre = testing.get("pre_commit", {})
        post = testing.get("post_commit", {})
        if pre.get("config_exists"):
            findings.append({
                "severity": "info",
                "title": "Pre-commit security scanning is configured",
                "file": ".pre-commit-config.yaml",
                "evidence": f"Hooks configured: {', '.join(pre.get('hooks', [])) or '(none detected)'}",
                "recommendation": "Confirm Ruff (S rules), detect-secrets and pip-audit are all present and run pre-commit run --all-files before each commit.",
            })
        else:
            findings.append({
                "severity": "high",
                "title": "No pre-commit security configuration found",
                "file": ".pre-commit-config.yaml",
                "evidence": "The file does not exist in the repository.",
                "recommendation": "Add .pre-commit-config.yaml with Ruff security rules, detect-secrets and pip-audit hooks.",
            })
        endpoint_tests = post.get("endpoint_test_files", [])
        findings.append({
            "severity": "info" if endpoint_tests else "medium",
            "title": "Post-commit endpoint test coverage",
            "file": ", ".join(endpoint_tests) if endpoint_tests else "(none found)",
            "evidence": f"{len(endpoint_tests)} test_post_commit_endpoints.py file(s) found across modules.",
            "recommendation": "Each student needs automated tests for at least two endpoint functions, wired into their own student-x.yml workflow.",
        })
        reports = testing.get("reports", [])
        findings.append({
            "severity": "info" if reports else "medium",
            "title": "Written testing evidence in docs/reports",
            "file": ", ".join(reports) if reports else "docs/reports/",
            "evidence": f"{len(reports)} matching report file(s) found." if reports else "No pre-commit/post-commit report documents found yet.",
            "recommendation": "Add each student's pre-commit security testing report and post-commit CI/CD testing report to docs/reports/.",
        })

    elif mode == "deployment":
        deployment = evidence.get("deployment", {})
        if deployment.get("cloud_deployment_workflow_exists"):
            findings.append({
                "severity": "info",
                "title": "cloud-deployment.yml workflow found",
                "file": "cloud-deployment.yml",
                "evidence": "The required cloud deployment CI/CD workflow file exists.",
                "recommendation": "Confirm it deploys with AI-Mode, MCP, RAG and Multi-Agent disabled by default.",
            })
        else:
            findings.append({
                "severity": "high",
                "title": "cloud-deployment.yml workflow not found",
                "file": "cloud-deployment.yml",
                "evidence": "Neither the repository root nor .github/workflows contains this file yet.",
                "recommendation": "Add the cloud-deployment.yml GitHub Actions workflow per the Release 2 brief.",
            })
        scripts = deployment.get("deploy_scripts", [])
        findings.append({
            "severity": "info" if scripts else "high",
            "title": "Cloud deployment scripts",
            "file": ", ".join(scripts) if scripts else "scripts/deploy/",
            "evidence": f"{len(scripts)} script(s) found in scripts/deploy/." if scripts else "scripts/deploy/ has no scripts yet (placeholder only).",
            "recommendation": "Add the Azure/AWS deployment script chain (env setup, build, deploy, deployment test, cleanup).",
        })
        reports = deployment.get("deployment_reports", [])
        findings.append({
            "severity": "info" if reports else "medium",
            "title": "Written deployment evidence in docs/reports",
            "file": ", ".join(reports) if reports else "docs/reports/",
            "evidence": f"{len(reports)} matching report file(s) found." if reports else "No deployment report document found yet.",
            "recommendation": "Add the cloud deployment report (deployed URL, CRUD verification, AI services disabled-by-default confirmation).",
        })

    return {
        "summary": (
            f"{LABELS[mode]} completed using deterministic repository checks because "
            "the configured LLM could not produce a usable response."
        ),
        "confidence": "medium",
        "findings": findings,
        "follow_up_paths": [],
    }

def _print_findings(findings):
    if not findings:
        print("  No findings were produced.")
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
    if mode in {"mcp", "rag", "multi_agent"}:
        _print_header(LABELS[mode].upper())
        if mode == "mcp":
            import asyncio
            live = asyncio.run(validate_mcp(repo_root=root))
        elif mode == "rag":
            live = validate_rag()
        else:
            live = validate_multi_agent()
        return 0 if print_validation(mode, live) else 1

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
            print(f"[WARN] LLM review unavailable: {review_error}")
            result = _deterministic_review(mode, evidence, paths)
            print("[INFO] Using deterministic review output.")

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
    keys = list(LABELS)
    for number, key in enumerate(keys, 1):
        print(f"  {number}. {LABELS[key]}")
    all_option = len(keys) + 1
    print(f"  {all_option}. All reviews + validations")
    print("  0. Exit")
    while True:
        value = input("Selection: ").strip()
        if value == "0":
            raise SystemExit(0)
        if value == str(all_option):
            return keys
        try:
            index = int(value) - 1
            if 0 <= index < len(keys):
                return [keys[index]]
        except ValueError:
            pass
        print(f"Choose 0-{all_option}.")

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
    failures = 0

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
                failures += int(result != 0)
            else:
                review_count += 1
                total += result
        except KeyboardInterrupt:
            print("\nInterrupted.")
            return 130
        except Exception as exc:
            print(f"[FAIL] {mode}: {type(exc).__name__}: {exc}")
            failures += 1

    print(
        f"\nSESSION COMPLETE: {review_count} review mode(s), "
        f"{validation_count} validation mode(s), {total} finding(s), {failures} failure(s)"
    )
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
