"""Let older deployment workflows finish before updating the shared Azure apps."""
import os
import time

import requests


def older_active(runs, current):
    return [r for r in runs if r["id"] < current and r["status"] not in {"completed"}]


if __name__ == "__main__":
    repo, current = os.environ["GITHUB_REPOSITORY"], int(os.environ["GITHUB_RUN_ID"])
    endpoint = f"https://api.github.com/repos/{repo}/actions/workflows/cloud-deployment.yml/runs"
    headers = {"Authorization": "Bearer " + os.environ["GH_ACTIONS_TOKEN"], "Accept": "application/vnd.github+json"}
    deadline = time.monotonic() + 1200
    while True:
        response = requests.get(endpoint, headers=headers, params={"per_page": 100}, timeout=30)
        response.raise_for_status()
        pending = older_active(response.json()["workflow_runs"], current)
        if not pending:
            print("No earlier cloud deployment remains active.")
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("An older deployment is still active. Retry this job after it finishes.")
        print("Waiting for older cloud runs: " + ", ".join(str(r["id"]) for r in pending), flush=True)
        time.sleep(15)
