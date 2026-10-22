#!/usr/bin/env bash
# Deploy the integrated Release 2 app to Azure Container Apps.
# Required: az CLI, Docker, an Azure subscription, and a pre-created resource group.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"
: "${AZURE_LOCATION:=australiaeast}"
: "${AZURE_CONTAINER_REGISTRY:?Set AZURE_CONTAINER_REGISTRY to a globally unique ACR name}"
: "${AZURE_CONTAINERAPPS_ENVIRONMENT:=finance-release2-env}"
: "${AZURE_STORAGE_ACCOUNT:?Set AZURE_STORAGE_ACCOUNT to a globally unique storage account name}"

# Unique image tag per deploy. With a fixed tag (release2) a code-only change
# leaves every Container App spec byte-for-byte identical, so Azure creates no
# new revision and keeps running the OLD image even though the new one was
# pushed. Tagging with the commit SHA (GitHub Actions sets GITHUB_SHA) changes
# the spec on every new commit and forces a fresh revision that pulls the new
# image. Note this also restarts the SQLite database containers, which resets
# their (ephemeral) data on every deploy.
IMAGE_TAG="${IMAGE_TAG:-release2-$(printf '%s' "${GITHUB_SHA:-$(date +%Y%m%d%H%M%S)}" | cut -c1-12)}"
echo "Using image tag: $IMAGE_TAG"

command -v az >/dev/null || { echo "Azure CLI (az) is required." >&2; exit 2; }
command -v docker >/dev/null || { echo "Docker is required (ACR Tasks is not available on this subscription, so images are built and pushed locally)." >&2; exit 2; }

# AI-Mode, MCP, RAG and Multi-Agent are all OFF by default (rubric: they must be
# disabled by default in the cloud). Each one is switched on only for the cloud
# AI bonus demo, by running the cloud-deployment workflow manually and ticking
# enable_ai_mode / enable_mcp / enable_rag / enable_multi_agent (or locally by
# exporting the matching *_ENABLED=true before running this script).
AI_ENABLED="${AI_ENABLED:-false}"
MCP_ENABLED="${MCP_ENABLED:-false}"
RAG_ENABLED="${RAG_ENABLED:-false}"
MULTI_AGENT_ENABLED="${MULTI_AGENT_ENABLED:-false}"
for flag in AI_ENABLED MCP_ENABLED RAG_ENABLED MULTI_AGENT_ENABLED; do
  if [[ "${!flag}" != "true" && "${!flag}" != "false" ]]; then
    echo "$flag must be 'true' or 'false' (got '${!flag}')." >&2
    exit 2
  fi
done
if [[ "$AI_ENABLED" != "true" ]] && [[ "$MCP_ENABLED" == "true" || "$RAG_ENABLED" == "true" || "$MULTI_AGENT_ENABLED" == "true" ]]; then
  echo "WARNING: MCP/RAG/Multi-Agent enabled without AI-Mode; the rubric's bonus tiers build on AI-Mode." >&2
fi
echo "Cloud AI toggles: AI_ENABLED=$AI_ENABLED MCP_ENABLED=$MCP_ENABLED RAG_ENABLED=$RAG_ENABLED MULTI_AGENT_ENABLED=$MULTI_AGENT_ENABLED"
# Shared secret between the five backends and the Multi-Agent server. A fresh
# random key is generated on every deploy unless one is supplied, so no key is
# stored in the repository.
MULTI_AGENT_API_KEY="${MULTI_AGENT_API_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
export AI_ENABLED MCP_ENABLED RAG_ENABLED MULTI_AGENT_ENABLED

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
az storage account create --name "$AZURE_STORAGE_ACCOUNT" --resource-group "$AZURE_RESOURCE_GROUP" --location "$AZURE_LOCATION" --sku Standard_LRS --kind StorageV2 --output none 2>/dev/null || true
STORAGE_KEY="$(az storage account keys list --account-name "$AZURE_STORAGE_ACCOUNT" --resource-group "$AZURE_RESOURCE_GROUP" --query '[0].value' --output tsv)"
for share in finance-db bill-db budget-db expense-db income-db savings-db; do
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

# Shared Ollama runtime + AI-Mode proxy, used only for the Release 2 cloud
# bonus (B1 Cloud AI-Mode and friends). Not part of the required baseline.
build_image ollama ./ai-services/ollama Dockerfile
build_image ai-mode ./ai-services/ai-mode Dockerfile

# MCP / RAG / Multi-Agent servers: cloud-only images, built only for a deploy
# that switches them on (locally they stay non-containerised host processes).
if [[ "$MCP_ENABLED" == "true" ]]; then build_image mcp-server ./ai-services/mcp-server Dockerfile; fi
if [[ "$RAG_ENABLED" == "true" ]]; then build_image rag-server ./ai-services/rag-server Dockerfile; fi
if [[ "$MULTI_AGENT_ENABLED" == "true" ]]; then build_image multi-agent-server ./ai-services/multi-agent-server Dockerfile; fi

# Create/update an app with a minimal YAML manifest. Database apps mount Azure Files at /data.
deploy_app() {
  local app="$1" image="$2" port="$3" ingress="$4" envs="$5" volume_share="${6:-}" cpu="${7:-}" memory="${8:-}"
  local manifest
  local ENV_DEFAULT_DOMAIN
  ENV_DEFAULT_DOMAIN="$(az containerapp env show --name "$AZURE_CONTAINERAPPS_ENVIRONMENT" --resource-group "$AZURE_RESOURCE_GROUP" --query properties.defaultDomain --output tsv)"
  local INTERNAL_SUFFIX="internal.$ENV_DEFAULT_DOMAIN"
  # Container-to-container calls must go through the environment's internal
  # ingress, which only listens on 443 (HTTPS) / 80 and then forwards to each
  # app's targetPort. Calling <app>.internal.<domain>:<targetPort> directly hits
  # a port nothing listens on, so every request silently times out. Use HTTPS
  # (not HTTP) because allowInsecure is false: plain HTTP gets a redirect, and
  # requests turns a redirected POST into a GET, which would break login etc.
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
  # Public (external) hostnames for browser-side cross-app navigation links
  # (Home buttons, "Open X Manager" links) -- these are followed by the
  # visitor's own browser, so they must be the real public HTTPS URL, not
  # the internal-only address used for container-to-container calls above.
  envs="${envs//http:\/\/finance-frontend:3000/https:\/\/finance-frontend.$ENV_DEFAULT_DOMAIN}"
  envs="${envs//http:\/\/budget-frontend:3001/https:\/\/budget-frontend.$ENV_DEFAULT_DOMAIN}"
  envs="${envs//http:\/\/expense-frontend:3002/https:\/\/expense-frontend.$ENV_DEFAULT_DOMAIN}"
  envs="${envs//http:\/\/income-frontend:3003/https:\/\/income-frontend.$ENV_DEFAULT_DOMAIN}"
  envs="${envs//http:\/\/bill-frontend:3004/https:\/\/bill-frontend.$ENV_DEFAULT_DOMAIN}"
  envs="${envs//http:\/\/savings-frontend:3005/https:\/\/savings-frontend.$ENV_DEFAULT_DOMAIN}"
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
      env_entries+="          - name: ${key}
            value: \"${value//\"/\\\"}\"
"
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
    # One replica for apps that keep state in memory or local disk: the SQLite
    # databases, the MCP server (Streamable HTTP sessions live in memory) and
    # the Multi-Agent server (run history in local SQLite).
    if [[ "$app" == *-database || "$app" == mcp-server || "$app" == multi-agent-server ]]; then local_max_replicas=1; fi
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

# Database APIs: internal-only SQLite files on the container's own local disk.
# They used to live on an Azure Files (SMB) share, but SQLite's file locking
# does not work reliably over SMB: finance-database crashed on startup with
# "sqlite3.OperationalError: database is locked" and restarted in a loop, so
# every login/register request timed out. Trade-off: data is ephemeral and is
# reset whenever a database container is redeployed or restarted (register a
# fresh account before each demo). /tmp is used because it exists and is
# writable in every image, including ones that run as a non-root user.
deploy_app finance-database finance-database 6000 false $'DATABASE_PATH=/tmp/finance.db'
deploy_app bill-database bill-database 6004 false $'DATABASE_PATH=/tmp/bills.db'
deploy_app budget-database budget-database 6001 false $'DATABASE_PATH=/tmp/budget_manager.db'
deploy_app expense-database expense-database 6002 false $'DATABASE_PATH=/tmp/expenses.db'
deploy_app income-database income-database 6003 false $'DATABASE_PATH=/tmp/student-3-income.db'
deploy_app savings-database savings-database 6005 false $'DATABASE_PATH=/tmp/savings.db'

# Shared Ollama runtime + AI-Mode proxy (cloud AI bonus). Internal-only.
# Always deployed so the AI toggle is just a flag flip; the backends only get
# an AI-Mode URL when AI_ENABLED=true (see below).
# 2 vCPU / 4Gi for ollama: LLM inference is much heavier than a REST call, and
# five modules (plus the Multi-Agent server's three agents) share this one
# runtime. (An earlier test removed this override; it was unrelated to the
# connectivity bug, which was the port-suffixed internal URLs.)
# OLLAMA_HOST is passed explicitly: the image's own ENV default was not applied
# at runtime and ollama listened on 127.0.0.1 only.
deploy_app ollama ollama 11434 false $'OLLAMA_HOST=0.0.0.0:11434' '' 2.0 4Gi
deploy_app ai-mode ai-mode 5099 false $'OLLAMA_URL=http://ollama:11434'

# MCP / RAG / Multi-Agent servers (cloud AI bonus). Internal-only. Deployed only
# when switched on; when switched off, any copy left over from an earlier bonus
# deploy is removed so the cloud matches the required baseline exactly.
deploy_or_remove() {
  local enabled="$1"; shift
  local app="$1"
  if [[ "$enabled" == "true" ]]; then
    deploy_app "$@"
  elif az containerapp show --name "$app" --resource-group "$AZURE_RESOURCE_GROUP" --output none 2>/dev/null; then
    echo "Removing $app (disabled for this deploy)"
    az containerapp delete --name "$app" --resource-group "$AZURE_RESOURCE_GROUP" --yes --output none
  fi
}
deploy_or_remove "$MCP_ENABLED" mcp-server mcp-server 5100 false $'PORT=5100\nEXPENSE_DB_URL=http://expense-database:6002\nBILL_DB_URL=http://bill-database:6004\nINCOME_DB_URL=http://income-database:6003\nSAVINGS_DB_URL=http://savings-database:6005\nBUDGET_DB_URL=http://budget-database:6001'
deploy_or_remove "$RAG_ENABLED" rag-server rag-server 5101 false $'PORT=5101\nAI_MODE_URL=http://ai-mode:5099\nRAG_GENERATION_TIMEOUT=150'
deploy_or_remove "$MULTI_AGENT_ENABLED" multi-agent-server multi-agent-server 5102 false $'MULTI_AGENT_HOST=0.0.0.0\nMULTI_AGENT_PORT=5102\nOLLAMA_URL=http://ollama:11434\nPLANNER_MODEL=qwen2.5:0.5b\nWORKER_MODEL=qwen2.5:0.5b\nREVIEWER_MODEL=qwen2.5:0.5b\nMULTI_AGENT_NUM_PREDICT=512\nMULTI_AGENT_DB_PATH=/tmp/multi-agent-runs.sqlite3\nMULTI_AGENT_API_KEY='"$MULTI_AGENT_API_KEY"

# Backends. AI_ENABLED follows the toggle above (default false). When it is on,
# each backend is also pointed at the shared AI-Mode service, using whichever
# variable name and path that module already reads locally. When it is off, no
# AI URL is passed at all, so modules whose code has no AI_ENABLED check of its
# own (bill, expense, income) cannot reach a model either.
if [[ "$AI_ENABLED" == "true" ]]; then
  BILL_AI=$'\nOLLAMA_URL=http://ai-mode:5099'
  BUDGET_AI=$'\nOLLAMA_URL=http://ai-mode:5099'
  EXPENSE_AI=$'\nOLLAMA_URL=http://ai-mode:5099'
  INCOME_AI=$'\nOLLAMA_BASE_URL=http://ai-mode:5099/v1\nOLLAMA_TIMEOUT_SECONDS=150'
  SAVINGS_AI=$'\nOLLAMA_API_URL=http://ai-mode:5099/api/generate'
else
  BILL_AI="" BUDGET_AI="" EXPENSE_AI="" INCOME_AI="" SAVINGS_AI=""
fi
# Same idea for MCP / RAG / Multi-Agent: the flag is always set explicitly, and
# the service URL is only passed when that service is switched on. Every
# backend reads the same variable names for these three.
FLAGS=$'\nAI_ENABLED='"$AI_ENABLED"$'\nMCP_ENABLED='"$MCP_ENABLED"$'\nRAG_ENABLED='"$RAG_ENABLED"$'\nMULTI_AGENT_ENABLED='"$MULTI_AGENT_ENABLED"
BONUS_URLS=""
if [[ "$MCP_ENABLED" == "true" ]]; then BONUS_URLS+=$'\nMCP_SERVER_URL=http://mcp-server:5100/mcp'; fi
if [[ "$RAG_ENABLED" == "true" ]]; then BONUS_URLS+=$'\nRAG_SERVER_URL=http://rag-server:5101'; fi
if [[ "$MULTI_AGENT_ENABLED" == "true" ]]; then BONUS_URLS+=$'\nMULTI_AGENT_URL=http://multi-agent-server:5102\nMULTI_AGENT_API_KEY='"$MULTI_AGENT_API_KEY"; fi
deploy_app finance-backend finance-backend 5000 false $'DATABASE_URL=http://finance-database:6000\nBILL_DATABASE_URL=http://bill-database:6004'
deploy_app bill-backend bill-backend 5004 false $'DATABASE_URL=http://bill-database:6004\nAUTH_DATABASE_URL=http://finance-database:6000'"$FLAGS$BILL_AI$BONUS_URLS"
deploy_app budget-backend budget-backend 5001 false $'DATABASE_URL=http://budget-database:6001\nAUTH_DATABASE_URL=http://finance-database:6000'"$FLAGS$BUDGET_AI$BONUS_URLS"
deploy_app expense-backend expense-backend 5002 false $'DATABASE_URL=http://expense-database:6002\nAUTH_DATABASE_URL=http://finance-database:6000'"$FLAGS$EXPENSE_AI$BONUS_URLS"
deploy_app income-backend income-backend 5003 false $'DATABASE_SERVICE_URL=http://income-database:6003\nAUTH_DATABASE_URL=http://finance-database:6000'"$FLAGS$INCOME_AI$BONUS_URLS"
deploy_app savings-backend savings-backend 5005 false $'DATABASE_API_URL=http://savings-database:6005\nAUTH_DATABASE_URL=http://finance-database:6000'"$FLAGS$SAVINGS_AI$BONUS_URLS"

# Frontends are the public entry points; they communicate with their internal backend apps.
deploy_app finance-frontend finance-frontend 3000 true $'BACKEND_URL=http://finance-backend:5000\nINCOME_URL=http://income-frontend:3003\nBILL_URL=http://bill-frontend:3004\nBUDGET_URL=http://budget-frontend:3001\nSAVINGS_URL=http://savings-frontend:3005\nEXPENSE_URL=http://expense-frontend:3002'
deploy_app budget-frontend budget-frontend 3001 true $'BACKEND_URL=http://budget-backend:5001\nFINANCE_URL=http://finance-frontend:3000'
deploy_app expense-frontend expense-frontend 3002 true $'BACKEND_URL=http://expense-backend:5002\nFINANCE_URL=http://finance-frontend:3000'
deploy_app income-frontend income-frontend 3003 true $'BACKEND_SERVICE_URL=http://income-backend:5003\nFINANCE_URL=http://finance-frontend:3000'
deploy_app bill-frontend bill-frontend 3004 true $'BACKEND_URL=http://bill-backend:5004\nFINANCE_URL=http://finance-frontend:3000'
deploy_app savings-frontend savings-frontend 3005 true $'BACKEND_API_URL=http://savings-backend:5005\nFINANCE_URL=http://finance-frontend:3000'

echo
echo "Checking deployed backend feature flags..."
# Every backend's four flags must match this deploy's toggles (all false by
# default, i.e. the required AI-disabled baseline).
for app in bill-backend budget-backend expense-backend income-backend savings-backend; do
  for flag in AI_ENABLED MCP_ENABLED RAG_ENABLED MULTI_AGENT_ENABLED; do
    expected="${!flag}"
    value="$(az containerapp show --name "$app" --resource-group "$AZURE_RESOURCE_GROUP" --query "properties.template.containers[0].env[?name=='$flag'].value | [0]" --output tsv)"
    if [[ "$value" != "$expected" ]]; then
      echo "ERROR: $app has $flag=$value (expected $expected)" >&2
      exit 1
    fi
  done
done

echo "Checking frontend HTTPS endpoints..."
for app in finance-frontend budget-frontend expense-frontend income-frontend bill-frontend savings-frontend; do
  url="$(az containerapp show --name "$app" --resource-group "$AZURE_RESOURCE_GROUP" --query properties.configuration.ingress.fqdn --output tsv)"
  printf 'Checking %-20s https://%s/ ... ' "$app" "$url"
  curl --fail --silent --show-error --location --max-time 20 --retry 12 --retry-delay 5 --retry-all-errors "https://$url/" --output /dev/null
  echo "OK"
done

echo "Checking frontend -> backend -> database chain..."
# The page checks above only prove the frontends serve HTML. This one goes
# finance-frontend -> finance-backend -> finance-database, so it fails if
# container-to-container networking is broken (which the page checks miss).
finance_url="$(az containerapp show --name finance-frontend --resource-group "$AZURE_RESOURCE_GROUP" --query properties.configuration.ingress.fqdn --output tsv)"
printf 'Checking https://%s/api/health ... ' "$finance_url"
health="$(curl --fail --silent --show-error --max-time 40 --retry 6 --retry-delay 10 --retry-all-errors "https://$finance_url/api/health")"
if ! grep -Eq '"status": ?"ok"' <<< "$health"; then
  echo "FAILED" >&2
  echo "$health" >&2
  exit 1
fi
echo "OK"

echo
echo "Deployment and basic endpoint smoke tests succeeded. Frontend URLs:"
for app in finance-frontend budget-frontend expense-frontend income-frontend bill-frontend savings-frontend; do
  url="$(az containerapp show --name "$app" --resource-group "$AZURE_RESOURCE_GROUP" --query properties.configuration.ingress.fqdn --output tsv)"
  printf '  %-20s https://%s\n' "$app" "$url"
done
