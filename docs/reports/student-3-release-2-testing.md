# Student 3 Release 2 testing report

Responsible feature: Income and Pay Schedule Manager. This contribution retains existing income/pay-schedule CRUD, shared authentication, AI-Mode, MCP and RAG while completing the Multi-Agent integration and shared review/deployment improvements. Earlier Release 2 work remains attributed to its original commits; this final contribution was developed with AI assistance and validated by tests.

## Pre-commit security testing

The repository installs real local Git hooks with `python -m pre_commit install`. Ruff 0.14.0 S rules, detect-secrets 1.5.0 and pip-audit execute during `git commit`. CI repeats the same full-repository checks. Hook output is retained under `docs/release-2/evidence/security/`; CI uploads its scan output separately.

The initial full scan identified 13 static warnings. Fixed SQL conditions and whitelisted editable column names continue to use bound parameters; narrowly scoped S608 annotations explain these reviewed false positives. Demo-only random dates and synthetic test credentials have specific annotations. HTTP calls in retained Budget MCP/RAG tests now have timeouts. No blanket addition to the existing ignored-rule list was needed. Secret references and generated credentials are distinguished from hardcoded secrets; real cloud mode refuses short development keys. The dependency audit covered 22 manifests with no known vulnerabilities at the audit time. The final commit-hook log is the source of truth for pass/fail.

The dated navigation diagnostics contain two public JavaScript SHA256 fingerprints. Their exact values were verified against the script bytes and narrowly recorded as false positives in the secrets baseline. No test password or session token is retained in those artifacts.

## Post-commit endpoint functions

`student-3.yml` runs `test_post_commit_endpoints.py` after a push. It tests authenticated `GET /api/income-sources` and `GET /api/pay-schedules`, confirms the backend forwards the authenticated owner ID, and saves a JUnit artifact. Those are backend route tests with mocked downstream replies. Real HTTP/database behavior is verified separately by the integrated Compose job and application smoke runner.

## Regression and integration coverage

The Student 3 plus agentic-loop suite passed 90 tests locally. Added boundaries cover absent authentication, attempts to inject another owner or forged evidence, disabled Multi-Agent avoiding database/model calls, owner-scoped history, human correction ownership and controlled server failure. The review CLI now propagates Multi-Agent failure and writes timestamped JSON/text logs. Three Node rendering tests verify escaped MCP/RAG output.

Shared tests verify that Income receives appropriate Worker instructions, Reviewer receives the plan and success criteria, all three agent stages appear in the audit log, and a second final decision is refused. Azure manifest tests exercise the actual shell function and verify HTTPS ingress URLs, immutable image tags, runtime secret references and all four flags in both profiles. Separate Budget database regressions prevent cross-user reads and modifications of budgets and categories.

The real temporary native stack completed 104 HTTP checks across shared login and all five feature modules, including CRUD, user isolation and disabled-mode responses. Its JSON is under `evidence/native/`; it is native validation, not a claim that Docker or Ollama ran here. GitHub's integrated Compose artifact must be used for container evidence. The actual local host AI servers, human review and screenshots must be demonstrated by the team.

## Review and release evidence

Run Testing Review only after retaining actual hook and post-push results. Run Multi-Agent Review against an exported workflow with a real final human decision. Run Deployment Review after retaining cloud artifacts. Fallback-only reviews are labelled and must not be described as a successful LLM-assisted review. Each student's individual hook execution, video participation and final human release decision remain personal evidence and must not be inferred from another student's test run.
