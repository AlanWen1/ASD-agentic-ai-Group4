"""Save real review output and inspect exported, human-reviewed workflows."""
import contextlib
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


class Tee(io.StringIO):
    def write(self, value):
        sys.__stdout__.write(value)
        return super().write(value)


def logged_review(root, output_dir, mode, model, model_available, action):
    started = datetime.now(timezone.utc)
    capture, result, error = Tee(), None, None
    try:
        with contextlib.redirect_stdout(capture):
            result = action()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + mode
        text = capture.getvalue()
        (output_dir / (stem + ".txt")).write_text(text + ("\n" + error if error else ""), encoding="utf-8")
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=10, check=False).stdout.strip()
        validation = mode in {"mcp", "rag", "multi_agent"}
        summary = {
            "mode": mode, "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(), "source_commit": "git:" + commit,
            "working_tree_dirty": bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, check=False).stdout.strip()),
            "model": model, "model_available": model_available,
            "method": "protocol_validation" if mode in {"mcp", "rag"} else ("deterministic_fallback" if not model_available or "deterministic review output" in text else "model_assisted"),
            "status": "failed" if error or (validation and result != 0) else "completed",
            "validation_exit_code": result if validation else None,
            "finding_count": result if not validation else None,
            "error": error, "output_file": stem + ".txt",
            "human_release_decision": "pending",
        }
        (output_dir / (stem + ".json")).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return result


def check_workflow(run):
    errors = []
    if not isinstance(run, dict):
        return ["Workflow evidence must be a JSON object"]
    if not isinstance(run.get("plan"), dict) or not run["plan"].get("steps"):
        errors.append("Planner steps are missing")
    if not isinstance(run.get("worker_output"), str) or not run["worker_output"].strip():
        errors.append("Worker output is missing")
    if not isinstance(run.get("review"), dict) or run["review"].get("verdict") not in {"pass", "needs_attention"}:
        errors.append("Reviewer assessment is missing or malformed")
    events = {(e.get("stage"), e.get("event")) for e in run.get("audit", []) if isinstance(e, dict)}
    for stage in ("planner", "worker", "reviewer"):
        if not {(stage, "started"), (stage, "completed")} <= events:
            errors.append(stage + " coordination events are missing")
    if run.get("status") not in {"approved", "rejected"} or not any(
        h.get("decision") in {"approve", "reject"} for h in run.get("history", []) if isinstance(h, dict)
    ):
        errors.append("A final real human approval or rejection has not been recorded")
    return errors
