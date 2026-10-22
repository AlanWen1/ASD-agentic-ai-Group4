"""Keep manual upstream switches compatible with strict baseline validation."""
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
FLAGS = ("AI_ENABLED", "MCP_ENABLED", "RAG_ENABLED", "MULTI_AGENT_ENABLED")


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/deploy" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("enabled", [("MCP_ENABLED",), ("AI_ENABLED", "RAG_ENABLED")])
def test_shell_retains_exact_manual_selection(enabled):
    source = (ROOT / "scripts/deploy/azure-deploy.sh").read_text()
    fragment = source[source.index('CLOUD_AI_PROFILE="'):source.index('IMAGE_TAG="')]
    flags = {name: "true" if name in enabled else "false" for name in FLAGS}
    command = fragment + '\nprintf "%s %s %s %s" "$AI_ENABLED" "$MCP_ENABLED" "$RAG_ENABLED" "$MULTI_AGENT_ENABLED"'
    result = subprocess.run(["bash", "-c", command], env={**os.environ,
        "CLOUD_AI_PROFILE": "baseline", **flags}, check=True, capture_output=True, text=True)
    assert result.stdout.split() == list(flags.values())


def test_workflow_defaults_every_manual_switch_off():
    workflow = yaml.safe_load((ROOT / ".github/workflows/cloud-deployment.yml").read_text())
    events = workflow.get("on", workflow.get(True))
    inputs = events["workflow_dispatch"]["inputs"]
    assert all(inputs[name]["default"] is False for name in
               ("enable_ai_mode", "enable_mcp", "enable_rag", "enable_multi_agent"))
    deploy = next(step for step in workflow["jobs"]["deploy"]["steps"] if step["name"] == "Deploy")
    assert all("github.event_name == 'workflow_dispatch'" in deploy["env"][name] for name in FLAGS)


def test_baseline_cannot_report_an_enabled_feature_as_passed(monkeypatch):
    module = load("verify_azure")
    for name in FLAGS:
        monkeypatch.setenv(name, "true" if name == "MCP_ENABLED" else "false")
    with pytest.raises(RuntimeError, match="Baseline must disable"):
        module.expected_flags("baseline")


def test_partial_verification_only_requires_selected_servers(monkeypatch):
    module = load("verify_azure")
    flags = {name: "true" if name == "MCP_ENABLED" else "false" for name in FLAGS}
    for name, value in flags.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("AZURE_RESOURCE_GROUP", "test")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "test")
    queried = []

    def azure(*args):
        if args[0] == "storage":
            return {"enableHttpsTrafficOnly": True, "minimumTlsVersion": "TLS1_2",
                "allowBlobPublicAccess": False, "encryption": {"services": {"file": {"enabled": True}}}}
        name = args[args.index("--name") + 1]
        queried.append(name)
        return {"properties": {"configuration": {"ingress": {"external": name.endswith("-frontend"),
            "allowInsecure": False, "fqdn": name + ".example.invalid"}}, "template": {"containers": [
                {"image": "example.invalid/" + name + ":test", "env": [
                    {"name": key, "value": value} for key, value in flags.items()]}]}}}

    monkeypatch.setattr(module, "azure", azure)
    result = module.verify("bonus")
    assert result["feature_flags"] == flags
    assert "mcp-server" in queried
    assert not {"ollama", "ai-mode", "rag-server", "multi-agent-server"} & set(queried)


def test_mcp_only_smoke_does_not_call_other_ai_services(monkeypatch):
    module = load("cloud_smoke")
    flags = {name: "true" if name == "MCP_ENABLED" else "false" for name in FLAGS}
    smoke = module.Smoke({"frontends": {}, "profile": "bonus", "feature_flags": flags})
    calls = []

    def call(_module, _method, path, *args, **kwargs):
        calls.append(path)
        return {"result": []}

    monkeypatch.setattr(smoke, "call", call)
    assert smoke.bonus() == {"mcp": {"result": []}}
    assert calls == ["/api/mcp/query"]
