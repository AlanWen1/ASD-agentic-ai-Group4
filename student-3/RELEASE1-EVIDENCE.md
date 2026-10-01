# Student 3 Release 1 evidence and contribution record

Owner: Yongjian Zhou. Baseline: `e75abd5` (shared MCP/RAG integration already
merged by the team). Working branch: `feature/student-3-release-1`.

## Changes in this follow-up

- Student 3 AI/MCP/RAG environment switches, with authenticated disabled-mode
  responses; default local behavior remains enabled.
- MCP ownership and tool allowlist tests; official SDK 2 result handling.
- RAG input, timeout, upstream failure, citation/confidence and insufficient-context
  validation; proxy tests and safe frontend text rendering.
- Student 3 Compose runs only frontend/backend/database; shared AI services run
  on the host. Standalone use requires the existing shared login service.
- Student 3 CI runs Python and frontend tests, builds containers and executes real
  HTTP CRUD/isolation/money checks with AI/MCP/RAG disabled.
- Shared agentic validator includes the ninth tool, checks downstream errors,
  validates five-feature retrieval and insufficient-context answers, and exits
  nonzero on failed validation.

Record the actual commit(s) after applying and reviewing these changes:

```powershell
git log -3 --format="%h %ad %an %s" --date=short
```

Do not attribute the baseline team's shared server work to this follow-up.

## Verified before patch delivery, 1 October 2026

| Check | Recorded result | Scope |
|---|---|---|
| Python tests with CI mode variables disabled | 78 passed | Student 3 and shared validator; enabled-mode dependencies mocked |
| Frontend rendering tests | 3 passed | Actual JavaScript handlers with minimal DOM |
| Native HTTP integration | Passed | Real auth/frontend/backend/SQLite Database API, disposable data |
| Live MCP protocol integration | Passed | Official SDK, actual MCP server and actual income DB, both income tools |
| Shared MCP negative case | Passed | Nine tools discovered; absent other module databases correctly fail |
| User's earlier Docker/UI check | User reported working | Capture formal screenshots/logs on the user's machine |
| Docker builds for this patch | Pending | Run locally and in GitHub Actions |
| GitHub Actions run for this patch | Pending | Save the successful run URL after push |

## Collect after applying the patch

1. Re-run tests and keep the console result. Push the feature branch with your own
   Git author identity. Record its actual commit hash and the successful Student 3
   workflow URL; if CI fails, fix it before calling the workflow successful.
2. Rebuild Student 3 in the integrated Compose project. Capture `docker compose
   ps -a`, showing the three Student 3 layers and all five integrated features.
3. Sign in through `http://localhost:3000`, open Income & Pay Schedule Manager,
   then capture MCP income sources and pay schedules results. Demonstrate one
   changed income record appearing in MCP output. Avoid tokens in screenshots.
4. Capture a RAG question such as `What is a pay schedule?`, including the answer,
   citation IDs and confidence category. Capture `Quantum chromodynamics` with
   insufficient confidence and empty citations.
5. With all five feature databases and the three host services running, collect
   shared validation output from a fresh PowerShell window at the repo root:

```powershell
New-Item -ItemType Directory -Force .\release1-evidence | Out-Null
$env:MCP_SERVER_URL = "http://localhost:5100/mcp"
$env:RAG_SERVER_URL = "http://localhost:5101"
$env:OLLAMA_URL = "http://localhost:11434"
# Default ID 1 is suitable for seeded demo data. Set your actual user ID if needed.
$env:VALIDATION_USER_ID = "1"
.\.venv\Scripts\python.exe .\ai-services\agentic-loop\agent_review.py --mode mcp 2>&1 | Tee-Object .\release1-evidence\mcp-validation.txt
$LASTEXITCODE
.\.venv\Scripts\python.exe .\ai-services\agentic-loop\agent_review.py --mode rag 2>&1 | Tee-Object .\release1-evidence\rag-validation.txt
$LASTEXITCODE
```

Both validation runs must end in an overall PASS and exit code 0. The shared MCP
run checks all nine tools, so every team's Database API must be available.

Also collect the four retained review modes (`database`, `implementation`,
`microservices`, `devops`) using the same reviewer with `llama3.1:8b`, and link
findings to the team's follow-up commits. A deterministic fallback should be
reported as such; do not claim that an unavailable model reviewed the code.

## Group submission still requires team evidence

The group report (maximum 3000 words), architecture diagrams, all five members'
CI/UI evidence, traceable contribution records and the video (maximum 10 minutes)
need the team's actual results. This patch completes the Student 3 follow-up code
and shared validator fixes; it does not create evidence for other members. Save
these records in the group's submission and export the final report as
`group-4.pdf` according to the brief. Deadline: 4 October 2026, 23:59 AEST.
