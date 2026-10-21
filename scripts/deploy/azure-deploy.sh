#!/usr/bin/env bash
# Deploy the integrated Release 2 app to Azure Container Apps.
# Required: az CLI, Docker, an Azure subscription, and a pre-created resource group.
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"
: "${AZURE_LOCATION:=australiaeast}"
: "${AZURE_CONTAINER_REGISTRY:?Set AZURE_CONTAINER_REGISTRY to a globally unique ACR name}"
: "${AZURE_CONTAINERAPPS_ENVIRONMENT:=finance-release2-env}"
: "${AZURE_STORAGE_ACCOUNT:?Set AZURE_STORAGE_ACCOUNT to a globally unique storage account name}"

command -v az >/dev/null || { echo "Azure CLI (az) is required." >&2; exit 2; }
command -v docker >/dev/null || { echo "Docker is required (ACR Tasks is not available on this subscription, so images are built and pushed locally)." >&2; exit 2; }

CLOUD_AI_PROFILE="${CLOUD_AI_PROFILE:-baseline}"
case "$CLOUD_AI_PROFILE" in
  baseline) AI_ENABLED=false ;;
  bonus) AI_ENABLED=true ;;
  *) echo "CLOUD_AI_PROFILE must be baseline or bonus" >&2; exit 2 ;;
esac
MCP_ENABLED="$AI_ENABLED"
RAG_ENABLED="$AI_ENABLED"
MULTI_AGENT_ENABLED="$AI_ENABLED"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short=12 HEAD)}"
export AI_ENABLED MCP_ENABLED RAG_ENABLED MULTI_AGENT_ENABLED
FRONTEND_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
MULTI_AGENT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  echo "::add-mask::$FRONTEND_SECRET"
  echo "::add-mask::$MULTI_AGENT_SECRET"
fi

echo "Checking Azure login and subscription..."
az account show --output none
az group show --name "$AZURE_RESOURCE_GROUP" --output none # Resource group must be pre-created; limits deploy identity scope.
az acr create --resource-group "$AZURE_RESOURCE_GROUP" --name "$AZURE_CONTAINER_REGISTRY" --sku Basic --admin-enabled false --output none 2>/dev/null || true
ACR_ID="$(az acr show --resource-group "$AZURE_RESOURCE_GROUP" --name "$AZURE_CONTAINER_REGISTRY" --query id --output tsv)"
ACR_LOGIN_SERVER="$(az acr show --resource-group "$AZURE_RESOURCE_GROUP" --name "$AZURE_CONTAINER_REGISTRY" --query loginServer --output tsv)"
# ACR Tasks (az acr build) is blocked on this subscription type (TasksOperationsNotAllowed),
# so images are built locally with docker and pushed directly to ACR instead.
az acr login --name "$AZURE_CONTAINER_REGISTRY" --output none
az containerapp env create --name "$AZURE_CONTAINERAPPS_ENVIRONMENT" --resource-group "$AZURE_RESOURCE_GROUP" --location "$AZURE_LOCATION" --output none 2>/dev/null || true

# Use managed identity for image pulls. Never put registry credentials in app settings.
IDENTITY_ID="$(az identity create --name finance-release2-acr-pull --resource-group "$AZURE_RESOURCE_GROUP" --location "$AZURE_LOCATION" --query id --output tsv)"
IDENTITY_PRINCIPAL="$(az identity show --name finance-release2-acr-pull --resource-group "$AZURE_RESOURCE_GROUP" --query principalId --output tsv)"
az role assignment create --assignee-object-id "$IDENTITY_PRINCIPAL" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID" --output none 2>/dev/null || true

# SQLite databases use Azure Files shares mounted at /data to survive container restarts.
az storage account create --name "$AZURE_STORAGE_ACCOUNT" --resource-group "$AZURE_RESOURCE_GROUP" --location "$AZURE_LOCATION" --sku Standard_LRS --kind StorageV2 --https-only true --min-tls-version TLS1_2 --allow-blob-public-access false --output none 2>/dev/null || true
az storage account update --name "$AZURE_STORAGE_ACCOUNT" --resource-group "$AZURE_RESOURCE_GROUP" --https-only true --min-tls-version TLS1_2 --allow-blob-public-access false --output none
STORAGE_KEY="$(az storage account keys list --account-name "$AZURE_STORAGE_ACCOUNT" --resource-group "$AZURE_RESOURCE_GROUP" --query '[0].value' --output tsv)"
for share in finance-db bill-db budget-db expense-db income-db savings-db multi-agent-db; do
  az storage share-rm create --resource-group "$AZURE_RESOURCE_GROUP" --storage-account "$AZURE_STORAGE_ACCOUNT" --name "$share" --quota 5 --output none 2>/dev/null || true
  az containerapp env storage set --name "$AZURE_CONTAINERAPPS_ENVIRONMENT" --resource-group "$AZURE_RESOURCE_GROUP" --storage-name "$share" --azure-file-account-name "$AZURE_STORAGE_ACCOUNT" --azure-file-account-key "$STORAGE_KEY" --azure-file-share-name "$share" --access-mode ReadWrite --output none
done

build_image() {
  local image="$1" context="$2" dockerfile="$3"
  local full_dockerfile="$dockerfile"
  # When context is a subdirectory, dockerfile is just a filename relative to it
  # (e.g. "Dockerfile"); when context is "." dockerfile is already a full
  # relative path from the repo root (e.g. "expense-category-tracker/frontend/Dockerfile").
  if [[ "$context" != "." && "$dockerfile" != /* ]]; then
    full_dockerfile="$context/$dockerfile"
  fi
  echo "Building $image using Dockerfile $full_dockerfile (context: $context)"
  docker build --tag "$ACR_LOGIN_SERVER/$image:$IMAGE_TAG" --file "$full_dockerfile" "$context"
  docker push "$ACR_LOGIN_SERVER/$image:$IMAGE_TAG"
}

# Build application services only. AI-Mode, MCP, RAG and Multi-Agent are deliberately excluded.
build_image finance-database ./finance-application/database Dockerfile
build_image finance-backend ./finance-application/backend Dockerfile
build_image finance-frontend ./finance-application/frontend Dockerfile
build_image bill-database ./bill-tracker/database Dockerfile
build_image bill-backend ./bill-tracker/backend Dockerfile
build_image bill-frontend ./bill-tracker/frontend Dockerfile
build_image budget-database ./student-1-budget/database Dockerfile
build_image budget-backend ./student-1-budget/backend Dockerfile
build_image budget-frontend . student-1-budget/frontend/Dockerfile
build_image expense-database ./expense-category-tracker/database Dockerfile
build_image expense-backend ./expense-category-tracker/backend Dockerfile
build_image expense-frontend . expense-category-tracker/frontend/Dockerfile
build_image income-database ./student-3/database Dockerfile
build_image income-backend ./student-3/backend Dockerfile
build_image income-frontend . student-3/frontend/Dockerfile
build_image savings-database ./student-5/database Dockerfile
build_image savings-backend ./student-5/backend Dockerfile
build_image savings-frontend . student-5/frontend/Dockerfile

if [[ "$CLOUD_AI_PROFILE" == "bonus" ]]; then
  build_image ollama ./ai-services/ollama Dockerfile
  build_image ai-mode ./ai-services/ai-mode Dockerfile
  build_image mcp-server ./ai-services/mcp-server Dockerfile
  build_image rag-server ./ai-services/rag-server Dockerfile
  build_image multi-agent-server ./ai-services/multi-agent-server Dockerfile
fi

# Create/update an app with a minimal YAML manifest. Database apps mount Azure Files at /data.
deploy_app() {
  local app="$1" image="$2" port="$3" ingress="$4" envs="$5" volume_share="${6:-}" cpu="${7:-}" memory="${8:-}"
  local manifest
  local ENV_DEFAULT_DOMAIN
  ENV_DEFAULT_DOMAIN="$(az containerapp env show --name "$AZURE_CONTAINERAPPS_ENVIRONMENT" --resource-group "$AZURE_RESOURCE_GROUP" --query properties.defaultDomain --output tsv)"
  local INTERNAL_SUFFIX="internal.$ENV_DEFAULT_DOMAIN"
  envs="${envs//http:\/\/finance-database:6000/https:\/\/finance-database.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/bill-database:6004/https:\/\/bill-database.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/budget-database:6001/https:\/\/budget-database.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/expense-database:6002/https:\/\/expense-database.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/income-database:6003/https:\/\/income-database.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/savings-database:6005/https:\/\/savings-database.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/finance-backend:5000/https:\/\/finance-backend.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/bill-backend:5004/https:\/\/bill-backend.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/budget-backend:5001/https:\/\/budget-backend.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/expense-backend:5002/https:\/\/expense-backend.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/income-backend:5003/https:\/\/income-backend.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/savings-backend:5005/https:\/\/savings-backend.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/ollama:11434/https:\/\/ollama.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/ai-mode:5099/https:\/\/ai-mode.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/mcp-server:5100/https:\/\/mcp-server.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/rag-server:5101/https:\/\/rag-server.$INTERNAL_SUFFIX}"
  envs="${envs//http:\/\/multi-agent-server:5102/https:\/\/multi-agent-server.$INTERNAL_SUFFIX}"
  envs+=$'\nAPP_ENV=cloud'
  if [[ "$app" == *-frontend ]]; then
    envs+=$'\nFINANCE_URL=https://finance-frontend.'"$ENV_DEFAULT_DOMAIN"
  fi
  local secrets_yaml=""
  if [[ "$envs" == *"secretref:"* ]]; then
    secrets_yaml="    secrets:"
    if [[ "$envs" == *"secretref:frontend-session-key"* ]]; then
      secrets_yaml+=$'\n      - name: frontend-session-key\n        value: '"$FRONTEND_SECRET"
    fi
    if [[ "$envs" == *"secretref:multi-agent-key"* ]]; then
      secrets_yaml+=$'\n      - name: multi-agent-key\n        value: '"$MULTI_AGENT_SECRET"
    fi
  fi
  manifest="$(mktemp)"
  {
    printf 'name: %s\nlocation: %s\n' "$app" "$AZURE_LOCATION"
    cat <<YAML
type: Microsoft.App/containerApps
identity:
  type: UserAssigned
  userAssignedIdentities:
    "$IDENTITY_ID": {}
properties:
  managedEnvironmentId: $(az containerapp env show --name "$AZURE_CONTAINERAPPS_ENVIRONMENT" --resource-group "$AZURE_RESOURCE_GROUP" --query id --output tsv)
  configuration:
    activeRevisionsMode: single
$secrets_yaml
    registries:
      - server: $ACR_LOGIN_SERVER
        identity: $IDENTITY_ID
    ingress:
      external: $ingress
      targetPort: $port
      transport: auto
      allowInsecure: false
  template:
    containers:
      - name: $app
        image: $ACR_LOGIN_SERVER/$image:$IMAGE_TAG
YAML
    env_entries=""
    while IFS='=' read -r key value; do
      [[ -z "$key" ]] && continue
      if [[ "$value" == secretref:* ]]; then
        env_entries+="          - name: ${key}
            secretRef: ${value#secretref:}
"
      else
        env_entries+="          - name: ${key}
            value: \"${value//\"/\\\"}\"
"
      fi
    done <<< "$envs"
    if [[ -n "$env_entries" ]]; then
      printf '        env:\n%s' "$env_entries"
    else
      printf '        env: []\n'
    fi
    if [[ -n "$cpu" ]]; then
      printf '        resources:\n          cpu: %s\n          memory: %s\n' "$cpu" "$memory"
    fi
    if [[ -n "$volume_share" ]]; then
      cat <<YAML
        volumeMounts:
          - volumeName: data-volume
            mountPath: /data
    volumes:
      - name: data-volume
        storageType: AzureFile
        storageName: $volume_share
YAML
    fi
    local local_max_replicas=2
    if [[ "$app" == *-database ]]; then local_max_replicas=1; fi
    cat <<YAML
    scale:
      minReplicas: 1
      maxReplicas: $local_max_replicas
YAML
  } > "$manifest"

  if az containerapp show --name "$app" --resource-group "$AZURE_RESOURCE_GROUP" --output none 2>/dev/null; then
    az containerapp update --name "$app" --resource-group "$AZURE_RESOURCE_GROUP" --yaml "$manifest" --output none
  else
    az containerapp create --name "$app" --resource-group "$AZURE_RESOURCE_GROUP" --yaml "$manifest" --output none
  fi
  rm -f "$manifest"
}

# Database APIs: internal-only, persistent SQLite files.
deploy_app finance-database finance-database 6000 false $'DATABASE_PATH=/data/finance.db' finance-db
deploy_app bill-database bill-database 6004 false $'DATABASE_PATH=/data/bills.db' bill-db
deploy_app budget-database budget-database 6001 false $'DATABASE_PATH=/data/budget_manager.db' budget-db
deploy_app expense-database expense-database 6002 false $'DATABASE_PATH=/data/expenses.db' expense-db
deploy_app income-database income-database 6003 false $'DATABASE_PATH=/data/student-3-income.db' income-db
deploy_app savings-database savings-database 6005 false $'DATABASE_PATH=/data/savings.db' savings-db

# Bonus services are opt-in. Local Compose still contains no AI services.
ENV_DOMAIN="$(az containerapp env show --name "$AZURE_CONTAINERAPPS_ENVIRONMENT" --resource-group "$AZURE_RESOURCE_GROUP" --query properties.defaultDomain --output tsv)"
PUBLIC_HOME="https://finance-frontend.$ENV_DOMAIN"
if [[ "$CLOUD_AI_PROFILE" == "bonus" ]]; then
  deploy_app ollama ollama 11434 false '' '' 2.0 4Gi
  deploy_app ai-mode ai-mode 5099 false $'OLLAMA_URL=http://ollama:11434\nAI_MODE_TIMEOUT=180'
  MCP_ENV=$'EXPENSE_DB_URL=http://expense-database:6002\nBILL_DB_URL=http://bill-database:6004\nINCOME_DB_URL=http://income-database:6003\nSAVINGS_DB_URL=http://savings-database:6005\nBUDGET_DB_URL=http://budget-database:6001\nMCP_STATELESS=true'
  MCP_ENV+=$'\nMCP_ALLOWED_HOSTS='"mcp-server.internal.$ENV_DOMAIN"
  deploy_app mcp-server mcp-server 5100 false "$MCP_ENV"
  deploy_app rag-server rag-server 5101 false $'AI_MODE_URL=http://ai-mode:5099\nRAG_GENERATION_TIMEOUT=180'
  deploy_app multi-agent-server multi-agent-server 5102 false $'OLLAMA_URL=http://ollama:11434\nMULTI_AGENT_API_KEY=secretref:multi-agent-key\nMULTI_AGENT_DB_PATH=/data/runs.sqlite3\nMULTI_AGENT_OLLAMA_NUM_CTX=4096\nMULTI_AGENT_OLLAMA_NUM_PREDICT=512' multi-agent-db
fi

COMMON_AI="AI_ENABLED=$AI_ENABLED"$'\n'"MCP_ENABLED=$MCP_ENABLED"$'\n'"RAG_ENABLED=$RAG_ENABLED"$'\n'"MULTI_AGENT_ENABLED=$MULTI_AGENT_ENABLED"
COMMON_AI+=$'\nOLLAMA_URL=http://ai-mode:5099\nOLLAMA_MODEL=qwen2.5:0.5b\nOLLAMA_BASE_URL=http://ai-mode:5099/v1\nOLLAMA_API_URL=http://ai-mode:5099/api/generate\nMCP_SERVER_URL=http://mcp-server:5100/mcp\nRAG_SERVER_URL=http://rag-server:5101\nMULTI_AGENT_URL=http://multi-agent-server:5102\nMULTI_AGENT_API_KEY=secretref:multi-agent-key'

deploy_app finance-backend finance-backend 5000 false $'DATABASE_URL=http://finance-database:6000\nBILL_DATABASE_URL=http://bill-database:6004'
deploy_app bill-backend bill-backend 5004 false "$COMMON_AI"$'\nDATABASE_URL=http://bill-database:6004\nAUTH_DATABASE_URL=http://finance-database:6000'
deploy_app budget-backend budget-backend 5001 false "$COMMON_AI"$'\nDATABASE_URL=http://budget-database:6001\nAUTH_DATABASE_URL=http://finance-database:6000'
deploy_app expense-backend expense-backend 5002 false "$COMMON_AI"$'\nDATABASE_URL=http://expense-database:6002\nAUTH_DATABASE_URL=http://finance-database:6000'
deploy_app income-backend income-backend 5003 false "$COMMON_AI"$'\nDATABASE_SERVICE_URL=http://income-database:6003\nAUTH_DATABASE_URL=http://finance-database:6000'
deploy_app savings-backend savings-backend 5005 false "$COMMON_AI"$'\nDATABASE_API_URL=http://savings-database:6005\nAUTH_DATABASE_URL=http://finance-database:6000'

HOME_ENV=$'BACKEND_URL=http://finance-backend:5000'
for module in budget expense income bill savings; do
  HOME_ENV+=$'\n'"${module^^}_FRONTEND_URL=https://$module-frontend.$ENV_DOMAIN"
done
deploy_app finance-frontend finance-frontend 3000 true "$HOME_ENV"
deploy_app budget-frontend budget-frontend 3001 true $'BACKEND_URL=http://budget-backend:5001'
deploy_app expense-frontend expense-frontend 3002 true $'BACKEND_URL=http://expense-backend:5002\nSECRET_KEY=secretref:frontend-session-key'
deploy_app income-frontend income-frontend 3003 true $'BACKEND_SERVICE_URL=http://income-backend:5003'
deploy_app bill-frontend bill-frontend 3004 true $'BACKEND_URL=http://bill-backend:5004'
deploy_app savings-frontend savings-frontend 3005 true $'BACKEND_API_URL=http://savings-backend:5005'

mkdir -p docs/release-2/evidence/cloud
python scripts/deploy/verify_azure.py --profile "$CLOUD_AI_PROFILE" --output docs/release-2/evidence/cloud/azure-controls.json
python scripts/deploy/cloud_smoke.py --deployment docs/release-2/evidence/cloud/azure-controls.json --output docs/release-2/evidence/cloud/application-tests.json
