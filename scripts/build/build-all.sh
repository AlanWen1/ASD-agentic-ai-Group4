#!/usr/bin/env bash
# Builds every service's Docker image using the root docker-compose.yml.
# Run from anywhere; this script cds to the repository root first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

echo "Building all services defined in docker-compose.yml..."
docker compose build

echo "Done. Run 'docker compose up' to start the integrated application."
