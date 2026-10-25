# Cloud Deployment Report – Release 2 (Microsoft Azure)

**Repository:** AlanWen1/ASD-agentic-ai-Group4 (branch `main`)
**Workflow:** `.github/workflows/cloud-deployment.yml` · **Script:** `scripts/deploy/azure-deploy.sh` (tear-down: `azure-destroy.sh`)
**Agentic-loop review of this report:** [`review-cloud-deployment.log`](review-cloud-deployment.log)

## 1. Target environment

| Item | Value |
|---|---|
| Platform | Azure Container Apps (region `australiaeast`), environment `finance-release2-env` |
| Images | Built by the workflow and pushed to Azure Container Registry, tagged `release2-<commit SHA>` so every commit creates a new revision |
| Registry access | User-assigned managed identity `finance-release2-acr-pull` with the AcrPull role (no registry password) |
| GitHub → Azure login | OpenID Connect (`azure/login`, secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, environment `azure-release2`) – no stored Azure credentials |
| Public apps | 6 frontends only (finance, budget, expense, income, bill, savings) – HTTPS ingress |
| Internal apps | 6 backends and 6 databases – internal ingress, reachable only inside the environment as `https://<app>.internal.<env-domain>` |
| Data | SQLite in each database container (`/tmp/<name>.db`, seeded on start; reset on each deploy) |

## 2. Deployment pipeline

1. `git push` to `main` (code has already passed the local pre-commit security hooks).
2. **validate** job – compiles every Python module, runs all five students' post-commit endpoint tests,
   and validates the Docker Compose configuration with AI services disabled.
3. **deploy** job (`needs: validate`) – OIDC login to Azure, then runs `azure-deploy.sh`, which builds and
   pushes every image, creates/updates each Container App, rewrites service URLs to internal HTTPS
   addresses and stores secrets as Container Apps secrets.
4. **Post-deploy smoke tests in the script** (the job fails if any check fails):
   - every backend's `AI_ENABLED`, `MCP_ENABLED`, `RAG_ENABLED`, `MULTI_AGENT_ENABLED` matches the run's toggles;
   - all six frontends answer over HTTPS;
   - `https://<finance-frontend>/api/health` returns `"status": "ok"` (frontend → backend → database chain);
   - endpoint security: only `*-frontend` apps are public, `http://` redirects to HTTPS,
     unauthenticated `GET /api/budgets` returns 401, and HSTS / X-Content-Type-Options /
     X-Frame-Options / Referrer-Policy headers are present.
5. The job summary lists the frontend URLs and the state of each AI service.

## 3. AI services disabled by default

AI-Mode, MCP, RAG and the Multi-Agent Server default to `false` in `azure-deploy.sh`. A push-triggered
deployment always deploys with all four disabled; the AI containers (Ollama, MCP, RAG, Multi-Agent) are
not deployed. They can only be enabled for the bonus demonstration by starting the workflow manually
(`workflow_dispatch`) and ticking `enable_ai_mode`, `enable_mcp`, `enable_rag` or `enable_multi_agent`.

## 4. Deployment evidence

| Evidence | Location |
|---|---|
| Successful baseline (push) run of `cloud-deployment.yml` | _add GitHub Actions run URL + screenshot_ |
| Smoke-test and security-check output (`OK` lines) | _screenshot of the Deploy step log_ |
| Job summary showing AI services disabled | _screenshot_ |
| Deployed frontend URL | _https://finance-frontend.…azurecontainerapps.io_ |
| Login + CRUD in each student's module on the cloud UI | _one screenshot per student_ |

## 5. Known limitations

- Cloud data is ephemeral: SQLite files live in the container and are re-seeded on every deployment
  (Azure Files/SMB was tried but caused "database is locked" errors).
- Images are built on the GitHub runner with Docker because ACR Tasks is unavailable on the subscription.

## 6. Final human release decision

| Item | Decision |
|---|---|
| Reviewed by | _name(s)_ |
| Date | _date_ |
| Evidence considered | validate job passed; deploy job passed with all smoke and security checks `OK`; cloud UI login and CRUD verified for all five modules; agentic-loop Cloud Deployment Review (`review-cloud-deployment.log`) reported 0 failures |
| Decision | **Approved for release** – _or_ Rejected / Approved with conditions |
| Conditions / follow-up | Cloud data resets on each deployment; AI services remain disabled in the baseline release |
