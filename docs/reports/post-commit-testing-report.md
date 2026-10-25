# Post-Commit CI/CD Endpoint Testing Report – Release 2

**Repository:** AlanWen1/ASD-agentic-ai-Group4 (branch `main`)
**Raw evidence:** [`post-commit-endpoint-tests.log`](post-commit-endpoint-tests.log)
**Agentic-loop review of this report:** [`review-testing.log`](review-testing.log)

## 1. Approach

Each student owns one GitHub Actions workflow (`.github/workflows/student-x.yml`). After code is pushed,
the workflow installs the module's dependencies, runs the module's existing unit tests, Docker
build/validation steps and then a dedicated **post-commit endpoint test** file that exercises two
endpoint functions of that student's backend/API service. Tests use Flask's `test_client()` with the
database-service call mocked (`monkeypatch`), so they run without containers and check three things:
HTTP status, response body, and that the request is scoped to the authenticated user.

The cloud workflow (`cloud-deployment.yml`) runs the same five endpoint test files in its `validate`
job before any deployment step, so a failing endpoint test blocks the Azure deployment.

## 2. Results per student

| Student | Workflow | Test file | Endpoint 1 | Endpoint 2 | Result |
|---|---|---|---|---|---|
| 1 – Budget Manager | `student-1.yml` | `student-1-budget/backend/test_post_commit_endpoints.py` | `GET /api/budgets` – lists budgets, forwards `user_id` | `GET /api/budgets/<id>` – returns one budget for the user | 2/2 passed |
| 2 – Expense & Category Manager | `student-2.yml` | `expense-category-tracker/backend/tests/test_post_commit_endpoints.py` | `GET /api/categories` – forwards the user to the database service | `GET /api/expenses?category_id=9` – forwards the category filter | 2/2 passed |
| 3 – Income Manager | `student-3.yml` | `student-3/tests/test_post_commit_endpoints.py` | `GET /api/income-sources` – bearer-token auth, user-scoped | `GET /api/pay-schedules` – bearer-token auth, user-scoped | 2/2 passed |
| 4 – Bills Manager | `student-4.yml` | `bill-tracker/backend/test_post_commit_endpoints.py` | `GET /bills` – user-scoped bill list | `GET /summary` – returns the backend summary | 2/2 passed |
| 5 – Savings Goal Manager | `student-5.yml` | `student-5/tests/test_post_commit_endpoints.py` | `GET /goals` – filters out other users' goals | `GET /goals/<id>` – calculates remaining amount and progress (750, 37.5 %) | 2/2 passed |

**Total: 10 passed, 0 failed.**

## 3. Workflow evidence

| Student | Trigger | Latest successful run (GitHub Actions) |
|---|---|---|
| 1 | push / PR touching `student-1-budget/**` | _add run URL + screenshot_ |
| 2 | push / PR touching `expense-category-tracker/**` | _add run URL + screenshot_ |
| 3 | push / PR touching `student-3/**` | _add run URL + screenshot_ |
| 4 | push / PR touching `bill-tracker/**` | _add run URL + screenshot_ |
| 5 | every push, PR to `main` | _add run URL + screenshot_ |

## 4. Notes

- The five test files share the basename `test_post_commit_endpoints.py`, so they must be run as
  separate pytest invocations (as each workflow does); running them in one pytest session causes an
  "import file mismatch".
- Local re-run command:
  `for t in <the five files above>; do python3 -m pytest -v -p no:cacheprovider "$t"; done`
