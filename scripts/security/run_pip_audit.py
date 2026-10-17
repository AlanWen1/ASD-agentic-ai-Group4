"""Audit repository requirements manifests with bounded parallel pip-audit runs."""
from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__"}
WORKERS = max(1, min(int(os.getenv("PIP_AUDIT_WORKERS", "4")), 8))
TIMEOUT_SECONDS = max(30, int(os.getenv("PIP_AUDIT_TIMEOUT_SECONDS", "120")))


def audit_manifest(manifest: Path) -> tuple[Path, int, str]:
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "--strict",
        "--requirement",
        str(manifest),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return (
            manifest,
            124,
            f"Timed out after {TIMEOUT_SECONDS}s while auditing "
            f"{manifest.relative_to(ROOT)}.",
        )

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return manifest, completed.returncode, output


def main() -> int:
    manifests = sorted(
        path
        for path in ROOT.rglob("requirements*.txt")
        if path.is_file() and not any(part in SKIP_PARTS for part in path.parts)
    )
    if not manifests:
        print("pip-audit: no requirements*.txt manifests found", file=sys.stderr)
        return 2

    failures = 0
    print(
        f"Auditing {len(manifests)} manifest(s) with {WORKERS} worker(s); "
        f"timeout={TIMEOUT_SECONDS}s per manifest.",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(audit_manifest, manifest): manifest for manifest in manifests}
        for future in as_completed(futures):
            manifest, return_code, output = future.result()
            print(f"\n=== pip-audit: {manifest.relative_to(ROOT)} ===", flush=True)
            print(output or "(no pip-audit output)", flush=True)
            if return_code:
                failures += 1
                print(
                    f"pip-audit failed for {manifest.relative_to(ROOT)} "
                    f"(exit {return_code})",
                    file=sys.stderr,
                    flush=True,
                )

    print(
        f"pip-audit summary: {len(manifests)} manifest(s), "
        f"{failures} failed audit(s).",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())