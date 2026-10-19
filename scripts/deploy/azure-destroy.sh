#!/usr/bin/env bash
# Explicitly destructive helper: removes the deployment resource group.
set -Eeuo pipefail
: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP to the exact resource group to delete}"
echo "This permanently deletes Azure resources in: $AZURE_RESOURCE_GROUP"
read -r -p "Type the resource group name to confirm: " confirmation
[[ "$confirmation" == "$AZURE_RESOURCE_GROUP" ]] || { echo "Confirmation did not match; nothing deleted."; exit 1; }
az group delete --name "$AZURE_RESOURCE_GROUP" --yes --no-wait