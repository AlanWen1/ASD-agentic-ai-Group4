"""Exercise the real shell manifest builder before it can change Azure resources."""
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/deploy/azure-deploy.sh"


@pytest.mark.parametrize("secret", [False, True])
def test_internal_ingress_url_image_and_secret_reference(tmp_path, secret):
    source = SCRIPT.read_text()
    function = "deploy_app() {" + source.split("deploy_app() {", 1)[1].split("\n# Database APIs", 1)[0]
    manifest = tmp_path / "manifest.yml"
    stub = '''az() {
      if [[ "$1 $2 $3" == "containerapp env show" ]]; then
        echo example.azurecontainerapps.io
      elif [[ "$1 $2" == "containerapp show" ]]; then
        return 1
      else
        while [[ $# -gt 0 ]]; do
          if [[ "$1" == "--yaml" ]]; then cp "$2" "$TEST_MANIFEST"; return 0; fi
          shift
        done
      fi
    }
    '''
    env = {**os.environ, "TEST_MANIFEST": str(manifest), "AZURE_LOCATION": "australiaeast",
           "AZURE_RESOURCE_GROUP": "test", "AZURE_CONTAINERAPPS_ENVIRONMENT": "test",
           "IDENTITY_ID": "/identities/test", "ACR_LOGIN_SERVER": "test.azurecr.io",
           "IMAGE_TAG": "commit123", "MULTI_AGENT_SECRET": "synthetic-fixture", "FRONTEND_SECRET": "synthetic-fixture"}  # pragma: allowlist secret -- synthetic fixture
    values = "DATABASE_SERVICE_URL=http://income-database:6003"
    if secret:
        values += "\nMULTI_AGENT_API_KEY=secretref:multi-agent-key"
    command = stub + function + '\ndeploy_app income-backend income-backend 5003 false "$TEST_VALUES"\n'
    subprocess.run(["bash", "-c", command], env={**env, "TEST_VALUES": values}, check=True, capture_output=True, text=True)
    data = yaml.safe_load(manifest.read_text())
    properties = data["properties"]
    assert properties["configuration"]["ingress"]["external"] is False
    assert properties["configuration"]["ingress"]["allowInsecure"] is False
    container = properties["template"]["containers"][0]
    assert container["image"] == "test.azurecr.io/income-backend:commit123"
    entries = {entry["name"]: entry for entry in container["env"]}
    assert entries["DATABASE_SERVICE_URL"]["value"] == "https://income-database.internal.example.azurecontainerapps.io"
    assert entries["APP_ENV"]["value"] == "cloud"
    if secret:
        assert entries["MULTI_AGENT_API_KEY"] == {"name": "MULTI_AGENT_API_KEY", "secretRef": "multi-agent-key"}  # pragma: allowlist secret -- reference name, no credential
        assert properties["configuration"]["secrets"][0]["name"] == "multi-agent-key"


@pytest.mark.parametrize("profile,expected", [("baseline", "false"), ("bonus", "true")])
def test_all_four_profile_flags_agree(profile, expected):
    source = SCRIPT.read_text()
    fragment = source[source.index('CLOUD_AI_PROFILE="'):source.index('IMAGE_TAG="')]
    command = fragment + '\nprintf "%s %s %s %s" "$AI_ENABLED" "$MCP_ENABLED" "$RAG_ENABLED" "$MULTI_AGENT_ENABLED"'
    # Test profile defaults independently of the workflow's explicit false flags.
    flags = {"AI_ENABLED", "MCP_ENABLED", "RAG_ENABLED", "MULTI_AGENT_ENABLED"}
    environment = {name: value for name, value in os.environ.items() if name not in flags}
    environment["CLOUD_AI_PROFILE"] = profile
    result = subprocess.run(["bash", "-c", command], env=environment, check=True, capture_output=True, text=True)
    assert result.stdout.split() == [expected] * 4


@pytest.mark.parametrize("profile", ["baseline", "bonus"])
def test_explicit_disabled_flags_override_profile_defaults(profile):
    source = SCRIPT.read_text()
    fragment = source[source.index('CLOUD_AI_PROFILE="'):source.index('IMAGE_TAG="')]
    command = fragment + '\nprintf "%s %s %s %s" "$AI_ENABLED" "$MCP_ENABLED" "$RAG_ENABLED" "$MULTI_AGENT_ENABLED"'
    flags = {name: "false" for name in ("AI_ENABLED", "MCP_ENABLED", "RAG_ENABLED", "MULTI_AGENT_ENABLED")}
    result = subprocess.run(["bash", "-c", command], env={**os.environ, **flags,
        "CLOUD_AI_PROFILE": profile}, check=True, capture_output=True, text=True)
    assert result.stdout.split() == ["false"] * 4


def test_deployment_requires_security_validation_before_mutation():
    workflow = yaml.safe_load((ROOT / ".github/workflows/cloud-deployment.yml").read_text())
    assert workflow["jobs"]["deploy"]["needs"] == "validate"
    validation = "\n".join(step.get("run", "") for step in workflow["jobs"]["validate"]["steps"])
    assert "pre-commit run --all-files" in validation
    assert "test_post_commit_endpoints" in validation


def test_local_compose_keeps_shared_ai_services_on_host():
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
    assert not {"ollama", "ai-mode", "mcp-server", "rag-server", "multi-agent-server"} & set(services)
