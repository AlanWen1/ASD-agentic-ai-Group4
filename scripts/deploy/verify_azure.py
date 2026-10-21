"""Read deployed Azure controls without exporting credential or secret values."""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MODULES = ("finance", "budget", "expense", "income", "bill", "savings")
AI_APPS = ("ollama", "ai-mode", "mcp-server", "rag-server", "multi-agent-server")


def azure(*args):
    result = subprocess.run(["az", *args, "--output", "json"], check=True,
                            capture_output=True, text=True, timeout=90)
    return json.loads(result.stdout)


def verify(profile):
    group = os.environ["AZURE_RESOURCE_GROUP"]
    report = {"observed_at": datetime.now(timezone.utc).isoformat(), "profile": profile, "environment": "azure",
              "commit": os.getenv("GITHUB_SHA"), "frontends": {}, "apps": {}, "checks": []}
    expected = "true" if profile == "bonus" else "false"
    names = [m + "-" + role for m in MODULES for role in ("frontend", "backend", "database")]
    if profile == "bonus":
        names.extend(AI_APPS)
    for name in names:
        data = azure("containerapp", "show", "--name", name, "--resource-group", group)
        properties = data["properties"]
        ingress = properties["configuration"]["ingress"]
        container = properties["template"]["containers"][0]
        env = {v["name"]: v for v in container.get("env", [])}
        public = name.endswith("-frontend")
        if bool(ingress.get("external")) != public or ingress.get("allowInsecure", False):
            raise RuntimeError(name + ": unexpected ingress exposure or insecure HTTP")
        if name.endswith("-backend") and name != "finance-backend":
            for flag in ("AI_ENABLED", "MCP_ENABLED", "RAG_ENABLED", "MULTI_AGENT_ENABLED"):
                if env.get(flag, {}).get("value") != expected:
                    raise RuntimeError(name + ": incorrect feature flag " + flag)
        for key in ("MULTI_AGENT_API_KEY", "SECRET_KEY"):
            if key in env and not env[key].get("secretRef"):
                raise RuntimeError(name + ": " + key + " must use an Azure secret reference")
        record = {"external_ingress": public, "allow_insecure": ingress.get("allowInsecure", False),
                  "image": container["image"], "secret_references": {
                      k: v["secretRef"] for k, v in env.items() if v.get("secretRef")},
                  "feature_flags": {k: v.get("value") for k, v in env.items() if k.endswith("_ENABLED")}}
        report["apps"][name] = record
        if public:
            report["frontends"][name.removesuffix("-frontend")] = "https://" + ingress["fqdn"]
    storage = azure("storage", "account", "show", "--name", os.environ["AZURE_STORAGE_ACCOUNT"],
                    "--resource-group", group)
    report["storage"] = {"https_only": storage.get("enableHttpsTrafficOnly"),
        "minimum_tls": storage.get("minimumTlsVersion"), "allow_blob_public_access": storage.get("allowBlobPublicAccess"),
        "files_encryption": storage.get("encryption", {}).get("services", {}).get("file", {}).get("enabled"),
        "key_source": storage.get("encryption", {}).get("keySource")}
    s = report["storage"]
    if not (s["https_only"] is True and s["minimum_tls"] == "TLS1_2"
            and s["allow_blob_public_access"] is False and s["files_encryption"] is True):
        raise RuntimeError("Azure Storage security controls did not match the required configuration")
    report["checks"] = ["HTTPS-only public frontends", "Backend/database/AI ingress is internal",
        "Cloud profile feature flags verified", "Secrets use secret references",
        "Azure Files encryption enabled", "Storage HTTPS and TLS 1.2 enforced", "Anonymous blob access disabled"]
    report["status"] = "passed"
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("baseline", "bonus"), default="baseline")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = verify(args.profile)
    except Exception as exc:
        target.write_text(json.dumps({"status": "failed", "error": str(exc), "profile": args.profile}, indent=2))
        raise
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[PASS] Azure ingress, feature flags, secret references and storage controls")
