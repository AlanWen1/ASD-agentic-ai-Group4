# Azure deployment and verification

Requires an existing Azure subscription/resource group, Azure CLI with Container Apps support, Docker, Git and Python with requests. Use the existing repository environment `azure-release2`, OIDC secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, and variables `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `AZURE_CONTAINER_REGISTRY`, `AZURE_CONTAINERAPPS_ENVIRONMENT`, `AZURE_STORAGE_ACCOUNT`. No client secret or storage key belongs in source control.

```bash
# Required deployment: all AI features disabled.
CLOUD_AI_PROFILE=baseline bash scripts/deploy/azure-deploy.sh
# Optional bonus, only after the baseline passes and its evidence is retained.
CLOUD_AI_PROFILE=bonus bash scripts/deploy/azure-deploy.sh
```

GitHub Actions exposes the same explicit baseline/bonus choice. Its default is baseline. The two named Release 2 final/bonus branches also support validation/deployment during this change; ordinary PRs only validate. All deployments share a concurrency group to avoid concurrent updates to the same Azure apps.

All internal service calls use HTTPS ingress FQDNs without target ports. Only frontends have external ingress. Public navigation and home URLs are configured during deployment. Images use the source commit as their tag. Runtime keys are generated and set through secret references; Azure Files credentials are used only for mounting storage. Local Docker Compose contains no AI services.

After deployment, `verify_azure.py` reads real ingress/flags/secret-reference/storage controls. `cloud_smoke.py` tests real registration/login and financial CRUD/owner isolation through all five public feature frontends. Bonus mode additionally executes the four AI capabilities. Both emit JSON artifacts, and failure stops the workflow. Financial test records are removed and sessions logged out; the two random test accounts remain. No test password/token is included in artifacts.

Keep baseline and bonus results separate in the report. A successful model workflow still needs a real human decision through the UI/terminal. The team must capture its own demo and local host-service evidence. Read `docs/release-2/README.md`, `docs/architecture/release-2.md` and the reports for the precise evidence boundaries. The destroy script permanently deletes the configured resource group and must only be used when deletion is actually intended.
