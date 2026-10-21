# Release 2 deployment report

## Verified locally in this change

The temporary native stack runs the same frontend/backend/database Python sources with isolated SQLite files. The integrated smoke test passed 71 HTTP checks: shared registration/login, owner-scoped CRUD across all five features, unauthenticated refusal, cross-user refusal and disabled AI/MCP/RAG/Multi-Agent endpoints. Financial test records are removed and sessions logged out. Test databases/server logs are temporary. The output identifies the execution environment explicitly.

The Azure manifest builder passed tests for HTTPS internal addresses without Docker target ports, external-ingress restrictions, secret references and immutable image tags. Baseline/bonus profile tests verify all four flags agree. These tests validate source behavior; they do not constitute cloud execution evidence.

## Automated container and Azure deployment

`cloud-deployment.yml` gates deployment on full pre-commit security checks, all students' two endpoint functions, regression checks, Compose validation and a real integrated container smoke test. It saves container evidence before Azure login. GitHub OIDC, ACR managed identity and reusable scripts deploy to the configured existing resource group.

`verify_azure.py` reads actual deployed app/storage configuration without exporting secret values. `cloud_smoke.py` then registers its own random test users, logs in and exercises the public frontend proxies through the internal backends/database APIs. A static HTML 200 response alone cannot pass. It verifies frontend security headers and profile behavior. Random test credentials are never logged; financial records are cleaned up. Two random smoke accounts remain because the public application has no account-deletion endpoint.

The baseline artifact must show all AI features disabled. A separate explicitly selected bonus run must show working AI-Mode, an MCP tool interaction, a RAG response with citations, and a three-agent run awaiting a real human decision. The deployment log/JSON status and source commit, not the existence of scripts or images, determine completion. Azure artifact links and live UI screenshots should be added to the final group report after the workflow runs.

## Human release decision

Pending until the team reviews actual cloud/core/bonus results and completes its UI demonstration. Do not replace this with an automated approval. Record the human's name, timestamp, decision, remaining limitations and corresponding workflow/review artifact links in the final report.
