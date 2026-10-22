# Release 2 deployment report

## Verified locally in this change

The temporary native stack runs the same frontend/backend/database Python sources with isolated SQLite files. The integrated smoke test passed 104 HTTP checks: shared registration/login, owner-scoped CRUD across all five features, unauthenticated refusal, cross-user refusal and disabled AI/MCP/RAG/Multi-Agent endpoints. It rereads records after updates and verifies that another account's mutation attempts leave the owner's data unchanged. Financial test records are removed and sessions logged out. Test databases/server logs are temporary. The output identifies the execution environment explicitly.

The Azure manifest builder passed tests for HTTPS internal addresses without Docker target ports, external-ingress restrictions, secret references and immutable image tags. Baseline/bonus profile tests verify all four flags agree. These tests validate source behavior; they do not constitute cloud execution evidence.

## Existing Azure baseline diagnostic — 22 October 2026

The team's [main deployment workflow](https://github.com/AlanWen1/ASD-agentic-ai-Group4/actions/runs/39712391466) completed successfully, but requests to the live site exposed two remaining acceptance failures. The served Finance JavaScript matched the earlier `1c1922a` file and retained five localhost module destinations despite the navigation fix in `d0f1fa9`. The deployment source still reused the mutable `:release2` image reference; an unchanged reference is consistent with Azure continuing to serve an older image. The candidate uses commit-specific image tags. Its smoke test also checks the JavaScript actually served, with regression tests for local destinations hidden in an otherwise valid HTTPS page.

Independent HTTP tests registered and logged in two random accounts. Income sources, pay schedules, Bills and the legacy Savings forms passed the attempted owner operations and read-isolation checks. Expense's legacy forms passed create/read/isolation checks; their update UI was not exercised. Budget's cross-account detail request returned HTTP 200 instead of refusing access. The candidate's Budget ownership regression prevents that access, but the deployed repair must still pass the cloud checks. All seven generated financial records were deleted and both sessions logged out. The two accounts remain because there is no account-deletion endpoint. Dated JSON under `evidence/cloud/20261022-*` records these partial results; it is not a successful final baseline artifact or an authenticated browser demonstration.

The team subsequently added the same commit-specific image-tag repair in `6800ad2`. This candidate merges that work. Its [deployment run](https://github.com/AlanWen1/ASD-agentic-ai-Group4/actions/runs/39715601926) and the assets actually served must be checked before treating the earlier navigation failure as resolved.

## Automated container and Azure deployment

`cloud-deployment.yml` gates deployment on full pre-commit security checks, all students' two endpoint functions, regression checks, Compose validation and a real integrated container smoke test. It saves container evidence before Azure login. GitHub OIDC, ACR managed identity and reusable scripts deploy to the configured existing resource group.

`verify_azure.py` reads actual deployed app/storage configuration without exporting secret values. `cloud_smoke.py` then registers its own random test users, logs in and exercises the public frontend proxies through the internal backends/database APIs. A static HTML 200 response alone cannot pass. It verifies frontend security headers and profile behavior. Random test credentials are never logged; financial records are cleaned up. Two random smoke accounts remain because the public application has no account-deletion endpoint.

The team's current cloud database configuration uses container-local `/tmp` SQLite files to avoid the observed SMB file-locking startup failure. Cloud data may reset on restart/redeployment; the report must not describe those active files as persistent Azure Files data. Storage-account encryption results establish the configured account's controls, not the location or protection of each active application's database. Local Compose database volumes are unaffected.

The baseline artifact must show all AI features disabled. A separate explicitly selected bonus run must show working AI-Mode, an MCP tool interaction, a RAG response with citations, and a three-agent run awaiting a real human decision. The deployment log/JSON status and source commit, not the existence of scripts or images, determine completion. Azure artifact links and live UI screenshots should be added to the final group report after the workflow runs.

## Human release decision

Pending until the team reviews actual cloud/core/bonus results and completes its UI demonstration. Do not replace this with an automated approval. Record the human's name, timestamp, decision, remaining limitations and corresponding workflow/review artifact links in the final report.
