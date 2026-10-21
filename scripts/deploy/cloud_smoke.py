"""Real frontend -> backend -> database tests; optional real AI bonus interactions.

Only creates randomly named test users and their own financial records. Financial
records are removed in reverse dependency order. Credentials are never logged.
The two test accounts remain (there is no public account-deletion API).
"""
import argparse
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


class Smoke:
    def __init__(self, deployment):
        self.urls = deployment["frontends"]
        self.profile = deployment.get("profile", "baseline")
        self.records, self.log, self.headers = [], [], {}

    def call(self, module, method, path, body=None, expected=(200,), headers=None, timeout=60):
        response = requests.request(method, self.urls[module] + path, json=body,
                                    headers=self.headers if headers is None else headers, timeout=timeout)
        if response.status_code not in expected:
            raise RuntimeError(f"{module} {method} {path}: expected {expected}, got {response.status_code}")
        self.log.append({"module": module, "method": method, "path": path,
                         "status": response.status_code, "checked_at": datetime.now(timezone.utc).isoformat()})
        return response.json() if response.content else None

    def accounts(self):
        tokens = []
        for _ in range(2):
            username = "r2_smoke_" + secrets.token_hex(6)
            password = secrets.token_urlsafe(24)
            self.call("finance", "POST", "/api/auth/register", {
                "username": username, "email": username + "@example.invalid", "password": password}, expected=(201,), headers={})
            result = self.call("finance", "POST", "/api/auth/login", {
                "identifier": username, "password": password}, headers={})
            tokens.append({"Authorization": "Bearer " + result["token"]})
        self.headers, self.other = tokens

    @staticmethod
    def items(body):
        return body if isinstance(body, list) else body.get("items", [])

    def crud(self, module, path, payload, key="id", update=None, detail=True, resource_path=None):
        self.call(module, "GET", path, headers={}, expected=(401,))
        created = self.call(module, "POST", path, payload, expected=(201,))
        identifier = created[key]
        resource = (resource_path or path + "/{id}").format(id=identifier)
        self.records.append((module, resource))
        assert any(item[key] == identifier for item in self.items(self.call(module, "GET", path)))
        assert all(item[key] != identifier for item in self.items(self.call(module, "GET", path, headers=self.other, expected=(200, 403, 404))))
        if detail:
            self.call(module, "GET", resource)
            self.call(module, "GET", resource, headers=self.other, expected=(403, 404))
        changed = self.call(module, "PUT", resource, update or payload)
        if isinstance(changed, dict) and "error" in changed:
            raise RuntimeError("Update returned an application error")
        return identifier

    def bonus(self):
        for _ in range(12):
            try:
                self.call("income", "GET", "/api/ai/status", timeout=30)
                break
            except (requests.RequestException, RuntimeError):
                time.sleep(5)
        else:
            raise RuntimeError("Cloud AI-Mode did not become ready")
        ai = self.call("income", "POST", "/api/ai/analyse", {"month": "2099-01"}, timeout=220)
        if not ai.get("answer", "").strip():
            raise RuntimeError("AI-Mode returned no answer")
        mcp = self.call("income", "POST", "/api/mcp/query", {"tool": "get_income_sources"}, timeout=120)
        if mcp.get("error"):
            raise RuntimeError("MCP tool interaction failed")
        rag = self.call("income", "POST", "/api/rag/ask", {"query": "What is a pay schedule?"}, timeout=220)
        if not (rag.get("answer") and rag.get("citations") and rag.get("confidence_category") != "insufficient"):
            raise RuntimeError("RAG answer did not include grounded citations")
        run = self.call("income", "POST", "/api/multi-agent/run", {
            "task": "Review my income sources and expected versus received pay schedules. Identify missing evidence."},
            expected=(201,), timeout=235)
        if not (run.get("plan", {}).get("steps") and run.get("worker_output") and run.get("review")
                and run.get("status") == "awaiting_human_review"):
            raise RuntimeError("Cloud Multi-Agent workflow did not reach human review")
        return {"ai_answer": ai["answer"], "mcp": mcp, "rag": rag, "multi_agent": run,
                "human_review": "pending: use the UI; the smoke test never approves on a person's behalf"}

    def run(self):
        for module, url in self.urls.items():
            for attempt in range(12):
                try:
                    response = requests.get(url + "/", timeout=60)
                    if response.status_code < 500:
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)
            else:
                raise RuntimeError(module + " frontend did not become ready")
            response.raise_for_status()
            assert response.headers.get("X-Content-Type-Options") == "nosniff"
            assert response.headers.get("Referrer-Policy") == "no-referrer"
            if url.startswith("https:"):
                assert response.headers.get("Strict-Transport-Security")
            if module == "finance" and url.startswith("https:"):
                assert "http://localhost:" not in response.text
        self.accounts()
        bonus = None
        try:
            self.call("finance", "GET", "/api/health")
            budget = self.crud("budget", "/api/budgets", {"month": 1, "year": 2099, "status": "active"},
                               "budget_id", {"status": "archived"})
            self.crud("budget", f"/api/budgets/{budget}/categories", {"category_name": "Smoke", "allocated_amount": 25},
                      "category_id", {"category_name": "Smoke updated", "allocated_amount": 30}, detail=False,
                      resource_path="/api/categories/{id}")
            category = self.crud("expense", "/api/categories", {"name": "Smoke", "type": "Discretionary"},
                                 update={"name": "Smoke updated", "type": "Discretionary"}, detail=False)
            self.crud("expense", "/api/expenses", {"amount": 12.5, "description": "Smoke expense", "date": "2099-01-01", "category_id": category},
                      update={"amount": 13, "description": "Smoke updated", "date": "2099-01-01", "category_id": category})
            source = self.crud("income", "/api/income-sources", {"source_name": "Cloud smoke income", "income_type": "Freelance",
                "standard_amount": 1250.5, "payment_frequency": "monthly", "active": True}, update={"source_name": "Cloud smoke updated"})
            self.crud("income", "/api/pay-schedules", {"income_source_id": source, "expected_pay_date": "2099-01-15", "expected_amount": 1250.5, "status": "scheduled"},
                update={"status": "received", "received_date": "2099-01-15", "actual_amount": 1200})
            bill = {"name": "Cloud smoke bill", "amount": 25, "due_date": "2099-01-15", "frequency": "Monthly", "status": "Pending"}
            self.crud("bill", "/api/bills", bill, update={"name": "Cloud smoke updated"})
            goal = {"goal_name": "Cloud smoke goal", "target_amount": 1000, "current_amount": 100, "target_date": "2099-01-15"}
            self.crud("savings", "/api/goals", goal, "goal_id", {**goal, "goal_name": "Cloud smoke updated"})
            if self.profile == "bonus":
                bonus = self.bonus()
            else:
                for path, body in [("/api/ai/analyse", {"month": "2099-01"}),
                    ("/api/mcp/query", {"tool": "get_income_sources"}), ("/api/rag/ask", {"query": "pay schedule"}),
                    ("/api/multi-agent/run", {"task": "Review income"})]:
                    self.call("income", "POST", path, body, expected=(503,))
        finally:
            cleanup_errors = []
            for module, resource in reversed(self.records):
                try:
                    self.call(module, "DELETE", resource, expected=(200, 204))
                except (requests.RequestException, RuntimeError) as exc:
                    cleanup_errors.append(str(exc))
            if cleanup_errors:
                self.log.append({"cleanup_errors": cleanup_errors})
                raise RuntimeError("Financial test record cleanup failed")
            for token in (self.headers, self.other):
                self.call("finance", "POST", "/api/auth/logout", {"token": token["Authorization"][7:]}, headers=token)
        return bonus


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    smoke = Smoke(json.loads(Path(args.deployment).read_text()))
    report = {"environment": json.loads(Path(args.deployment).read_text()).get("environment", "unspecified"), "profile": smoke.profile, "started_at": datetime.now(timezone.utc).isoformat(), "checks": smoke.log}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        report["bonus"] = smoke.run()
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[PASS] Shared login, five modules' CRUD, owner isolation and cloud profile")
