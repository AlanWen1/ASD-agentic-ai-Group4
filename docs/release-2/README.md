# Release 2 delivery and evidence

The integrated application retains six frontend/backend/database stacks and four shared AI services. Local AI-Mode (5099), MCP (5100), RAG (5101), Multi-Agent (5102), Ollama and the agentic loop run as host processes, outside Docker Compose.

## What this branch completes

- Student 3 authenticated Multi-Agent integration, owner-scoped history, controlled disabled/error responses and workflow evidence download.
- Module-specific Worker instructions; Reviewer receives the complete Planner plan and success criteria. SQLite preserves agent start/completion events, timings, output hashes, correction cycles and actual human decisions. Existing run databases are migrated without deleting records.
- All three Release 2 review modes; timestamped text/JSON review logs; failed Multi-Agent validation now exits nonzero. Testing/deployment reviews receive actual report text. Workflow Review checks a real exported human-reviewed run, rather than claiming that an unfinished synthetic run is complete.
- Cloud navigation and return-home URLs supplied by environment configuration. Internal Azure HTTP calls use HTTPS ingress FQDNs, not Docker target ports.
- Budget/category ownership enforced for reads and mutations; Savings MCP results scoped to the supplied owner; public frontend security headers; secure cloud Expense sessions; escaped Savings goal names.
- Full-repository security scans, individual endpoint JUnit artifacts, integrated Compose/HTTP validation and immutable image tags.
- Explicit baseline/bonus cloud profiles; reusable deployment and real post-deployment CRUD/security/AI verification.

## Start locally on Windows

Run `scripts/windows/start-release2.ps1 -Install` from PowerShell. Docker Desktop and Ollama must already be available. The script installs the local commit hooks, starts four host AI server terminals and starts the core Compose application. Open http://localhost:3000 and use the shared login.

Use Income Manager's Multi-Agent panel. Inspect all three outputs, request a correction when appropriate, and make a real approval/rejection decision. Download the workflow JSON. The application never converts an AI review into a human approval automatically.

```powershell
.venv\Scripts\python.exe ai-services/agentic-loop/agent_review.py --mode multi_agent --workflow-evidence PATH_TO_DOWNLOADED_JSON --model qwen2.5:0.5b
.venv\Scripts\python.exe ai-services/agentic-loop/agent_review.py --mode testing --model qwen2.5:0.5b
.venv\Scripts\python.exe ai-services/agentic-loop/agent_review.py --mode deployment --model qwen2.5:0.5b
```

For terminal interaction use `ai-services/multi-agent-server/cli.py --module income --task "Review supplied income evidence" --evidence-file FILE.json --user-id YOUR_ID`. It prompts for the human decision and saves the full run.

## Cloud profiles

`cloud-deployment.yml` defaults to **baseline**: every backend has AI, MCP, RAG and Multi-Agent disabled. The current priority is a working baseline. Retain its successful deployment/application artifact and verify registration, login, cloud navigation and all five modules with local services stopped. The team's four manual feature checkboxes are retained for later work and default to false. Selecting any checkbox labels that run as bonus; validation checks the exact selected flags and leaves unselected features disabled. Do not enable them until the core cloud application is accepted. Both profiles use the existing Azure resource group and OIDC identity. No Azure credentials belong in the repository.

The deployment must pass whole-repository security checks, endpoint tests, regression tests and integrated container CRUD tests before Azure changes begin. It then verifies deployed ingress, feature flags, secret references and storage encryption/TLS settings, followed by actual login, CRUD and isolation requests through the public frontends. The bonus check also makes real AI/MCP/RAG/Multi-Agent requests. A green build alone is not deployment evidence.

## Evidence and honest completion

- `evidence/native/application-tests.json`: real native HTTP test output, explicitly not the required Docker deployment.
- GitHub Actions individual JUnit artifacts: post-push endpoint results.
- GitHub Actions `integrated-compose-tests`: real container integration results.
- GitHub Actions `cloud-baseline-*` / `cloud-bonus-*`: observed Azure controls and real application interactions.
- `evidence/reviews/`: generated text and JSON review logs, including failures and deterministic fallback labels.
- `evidence/multi-agent/`: terminal/UI workflow exports with actual human decisions.

Do not fabricate missing cloud, LLM, human-review or individual security evidence. Each student must retain their own local commit-hook output and explain their contribution. The final report must include the video URL (all members, maximum 10 minutes), contribution records, diagrams, review logs and a human release decision. Group report: **maximum 3000 words**, `group-04.pdf`, one group submission.
