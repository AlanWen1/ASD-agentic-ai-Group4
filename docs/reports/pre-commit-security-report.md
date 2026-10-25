# Pre-Commit Security Testing Report – Release 2

**Repository:** AlanWen1/ASD-agentic-ai-Group4 (branch `main`)
**Raw evidence:** [`pre-commit-security-scan.log`](pre-commit-security-scan.log)
**Agentic-loop review of this report:** [`review-testing.log`](review-testing.log)

## 1. Configuration

The scans are defined once in `.pre-commit-config.yaml` at the repository root and run automatically on
every `git commit` after `pre-commit install`. They can also be run on demand with
`python3 -m pre_commit run --all-files`. The same scans are repeated in GitHub Actions by
`.github/workflows/security-testing.yml`.

| Hook | Tool / version | What it checks | Arguments |
|---|---|---|---|
| Ruff security rules | ruff 0.14.0 (Bandit `S` rules) | Insecure Python patterns: SQL built from strings (S608), `eval`/`exec`, insecure hashing, `requests` without timeout, unsafe deserialisation, etc. | `--select=S --ignore=S101,S104,S105,S106,S110,S603,S607` |
| detect-secrets | detect-secrets 1.5.0 | Hard-coded passwords, API keys, tokens and high-entropy strings in staged files | `--baseline .secrets.baseline` |
| pip-audit | pip-audit 2.10.1 via `scripts/security/run_pip_audit.py` | Known CVEs/advisories in every `requirements*.txt` manifest (`--strict`) | runs on all manifests, 4 parallel workers, 120 s timeout each |

**Ignored Ruff rules (justification):** S101 `assert` (used in pytest), S104 bind to `0.0.0.0`
(required inside containers), S105/S106 hard-coded password strings (test fixtures; real secrets are
covered by detect-secrets), S110 `try/except/pass` (best-effort cleanup), S603/S607 `subprocess`
calls (fixed argument lists in the agentic loop and audit script, no shell).

## 2. Results

| Scan | Scope | Result |
|---|---|---|
| Ruff S rules | 75 tracked Python files | **Passed** – 0 findings |
| detect-secrets | all tracked files | **Passed** – no new secrets; 5 audited test-fixture values in the baseline |
| pip-audit | 22 dependency manifests | **Passed** – no known vulnerabilities in any manifest |

## 3. Findings and resolution

| Finding | Where | Resolution |
|---|---|---|
| S608 – SQL statement built with an f-string | database services | Column names are now taken only from an allow-list of known fields and all values are bound with `?` parameters. The 4 remaining dynamic statements carry a reviewed `# noqa: S608`: `bill-tracker/database/app.py:168`, `finance-application/database/app.py:215`, `student-3/database/app.py:302`, `student-3/database/app.py:403`. Fixed in commits `86a8e84`, `899548f` and `57c667b`. |
| `.secrets.baseline` was an accidental copy of the pre-commit config | repository root | Baseline regenerated (`17a1879`) so detect-secrets compares against real audited results. |
| Secret-keyword matches in test fixtures | `student-1-budget/tests/test_budget_api.py` (lines 15, 60), `student-1-budget/tests/test_mcp_rag.py` (38, 43), `student-5/tests/test_savings_goal_api.py` (17) | Dummy test credentials only; reviewed and recorded in `.secrets.baseline`. Production secrets are generated at deploy time and stored as Azure Container Apps secrets (see the cloud deployment report). |
| Transient network error during pip-audit | `ai-services/ai-mode/requirements.txt` | `IncompleteRead` while downloading the index; re-run of that manifest reported no known vulnerabilities. |

## 4. Per-student coverage

| Student | Module | Ruff S | detect-secrets | pip-audit manifests |
|---|---|---|---|---|
| Student 1 | Budget Manager (`student-1-budget/`) | Passed | Passed (4 baselined fixtures) | backend, database, frontend, requirements-dev |
| Student 2 | Expense & Category Manager (`expense-category-tracker/`) | Passed (no suppressions) | Passed | backend, database, frontend |
| Student 3 | Income Manager (`student-3/`) | Passed (2 reviewed S608) | Passed | backend, database, frontend |
| Student 4 | Bills Manager (`bill-tracker/`) | Passed (1 reviewed S608) | Passed | backend, database, frontend |
| Student 5 | Savings Goal Manager (`student-5/`) | Passed | Passed (1 baselined fixture) | no `requirements.txt` – dependencies installed directly in `student-5.yml` |
| Shared | `ai-services/`, `finance-application/` | Passed (1 reviewed S608) | Passed | 5 AI-service manifests, 3 finance-application manifests, root `requirements-dev.txt` |

**Known limitation:** Student 5's module has no `requirements*.txt`, so its dependencies (`flask`,
`requests`, `mcp`) are not covered by pip-audit. Adding a manifest would bring it into the scan.
