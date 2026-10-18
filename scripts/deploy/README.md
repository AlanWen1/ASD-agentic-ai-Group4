# Azure deployment — Release 2 integrated application

Reusable scripts for deploying the integrated six-module application to Azure Container Apps.

## Architecture

- Azure Container Registry (ACR) builds and stores the application images.
- Azure Container Apps runs the six frontend apps, six backend/API apps and six database API apps.
- Frontends receive public HTTPS ingress. Backends and database APIs use internal ingress.
- Each SQLite database has a separate Azure Files share mounted at `/data`, so data persists across container replacement.
- AI-Mode, MCP, RAG and Multi-Agent services are not built or deployed. Related feature flags are explicitly set to `false`.

## Prerequisites and GitHub configuration

You need an Azure subscription. Create the resource group in Azure beforehand; this keeps the GitHub deploy identity scoped to that resource group. Configure the GitHub OIDC identity with Contributor and User Access Administrator permissions scoped to the resource group (the script creates a managed identity and grants it AcrPull on ACR). Configure a federated identity credential to trust the GitHub repository and the `azure-release2` GitHub Actions environment. Do not save an Azure client secret in the repository.

Set these **GitHub repository variables**:

- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION` (for example, `australiaeast`)
- `AZURE_CONTAINER_REGISTRY` (globally unique ACR name)
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_STORAGE_ACCOUNT` (globally unique lowercase storage account name)

Set these **GitHub Actions secrets**:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

The Azure identity needs permissions to create/update these resources and assign `AcrPull` to the managed identity.

## Deploy locally

From the repository root:

```bash
az login
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
export AZURE_RESOURCE_GROUP=rg-finance-release2
export AZURE_LOCATION=australiaeast
export AZURE_CONTAINER_REGISTRY=yourgloballyuniqueacr
export AZURE_CONTAINERAPPS_ENVIRONMENT=finance-release2-env
export AZURE_STORAGE_ACCOUNT=yourgloballyuniquestorage
bash scripts/deploy/azure-deploy.sh
```

Before running the script, create the resource group once (Azure Portal or `az group create --name "$AZURE_RESOURCE_GROUP" --location "$AZURE_LOCATION"`). The script verifies that it exists, builds images from the repository Dockerfiles, creates the Azure Files shares and apps, checks the AI/MCP/RAG/Multi-Agent flags remain false, probes each public frontend over HTTPS, and prints the URLs only after those checks pass. It expects the Azure CLI and Container Apps support to be installed. The optional `azure-destroy.sh` script permanently deletes the configured resource group after requiring you to type its exact name; use it only when you intend to delete all resources and stored data.

## Automated deployment

`.github/workflows/cloud-deployment.yml` runs integrated validation before deployment. Deployment runs on pushes to `main` or a manual workflow dispatch, and only after the validation job succeeds. It authenticates with Azure using GitHub OIDC.

The workflow file must first be merged into the repository's default branch for the **Run workflow** button to appear. After setting up the variables, secrets, GitHub environment and Azure federated credential, open **Actions → Release 2 Azure Cloud Deployment → Run workflow** and select the deployment branch. Alternatively, merging the configured deployment changes to `release-2-security-endpoint-testing` triggers the workflow on that branch. A green workflow run, with both `validate` and `deploy` jobs successful, is required before claiming that Azure deployment succeeded.

## Smoke tests and operational notes

After deployment, open each printed frontend HTTPS URL and verify login/session hand-off and CRUD workflows for all five modules. Inspect Container Apps logs and verify database persistence across a revision restart. Local SQLite data is not migrated automatically.

The services use SQLite behind HTTP database APIs. Azure Files preserves the existing design with minimal changes; it is appropriate for a coursework deployment, not a recommendation for high-concurrency production workloads. Before production use, review authentication and authorization, backups and restore, private networking, monitoring, rate limits and managed database options.