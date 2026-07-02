#!/usr/bin/env python3
"""Build the Cloudflare Worker by embedding support scripts and manifest data."""

import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER_DIR = os.path.join(REPO_ROOT, "worker")
ARTIFACT_VERSION = os.environ.get("SUPPORT_ARTIFACT_VERSION", "dev")
# The instance's serving domain. Deployed instances (worker/deploy.sh, or the
# private ZenuxLabs/support-cloud config) set SUPPORT_BASE_URL to their own host;
# the OSS engine hardcodes no domain. A raw build with no value leaves the
# {{SUPPORT_BASE_URL}} placeholder empty, and the scripts fail loudly rather than
# silently pulling from someone else's host.
BASE_URL = os.environ.get("SUPPORT_BASE_URL", "")

# Operating-instance config injected into served scripts at build time. The OSS
# defaults are empty, so a self-hosted build leaves join.ps1's key prompt intact
# and bakes in no domain; a private instance (e.g. ZenuxLabs/support-cloud) sets
# SUPPORT_AUTHORIZED_KEY / SUPPORT_BASE_URL to bake in its own support pubkey and
# serving host. A public SSH key is not a secret.
SUPPORT_AUTHORIZED_KEY = os.environ.get("SUPPORT_AUTHORIZED_KEY", "")
INSTANCE_SUBSTITUTIONS = {
    "{{SUPPORT_AUTHORIZED_KEY}}": SUPPORT_AUTHORIZED_KEY,
    "{{SUPPORT_BASE_URL}}": BASE_URL,
}


def js_template_literal(content):
    escaped = content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    return escaped


def read_text(filepath):
    with open(filepath, encoding="utf-8") as f:
        return f.read()


def processed_content(filepath):
    """Script content with instance-config substitutions applied. Used for both
    the embedded body and the manifest hash so they always match."""
    content = read_text(filepath)
    for token, value in INSTANCE_SUBSTITUTIONS.items():
        content = content.replace(token, value)
    return content


def sha256_text(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


SCRIPT_ARTIFACTS = [
    {
        "placeholder": "JOIN_PS1",
        "name": "join.ps1",
        "path": os.path.join(
            REPO_ROOT, "scripts", "windows", "onboarding", "join.ps1"
        ),
        "platform": "windows",
        "purpose": "join-bootstrap",
    },
    {
        "placeholder": "CRASH_CHECK_PS1",
        "name": "crash-check.ps1",
        "path": os.path.join(
            REPO_ROOT, "scripts", "windows", "diagnostics", "crash-check.ps1"
        ),
        "platform": "windows",
        "purpose": "diagnostics",
    },
    {
        "placeholder": "CUSTOMER_SSH_BOOTSTRAP_PS1",
        "name": "customer-ssh-bootstrap.ps1",
        "path": os.path.join(
            REPO_ROOT,
            "scripts",
            "windows",
            "onboarding",
            "customer-ssh-bootstrap.ps1",
        ),
        "platform": "windows",
        "purpose": "bootstrap",
    },
    {
        "placeholder": "WINDOWS_SSH_ONBOARD_PS1",
        "name": "windows-ssh-onboard.ps1",
        "path": os.path.join(
            REPO_ROOT, "scripts", "windows", "onboarding", "windows-ssh-onboard.ps1"
        ),
        "platform": "windows",
        "purpose": "ssh-onboard",
    },
    {
        "placeholder": "WINDOWS_SSH_OFFBOARD_PS1",
        "name": "windows-ssh-offboard.ps1",
        "path": os.path.join(
            REPO_ROOT, "scripts", "windows", "offboarding", "windows-ssh-offboard.ps1"
        ),
        "platform": "windows",
        "purpose": "ssh-offboard",
    },
    {
        "placeholder": "RUN_VERIFIED_PS1",
        "name": "run-verified.ps1",
        "path": os.path.join(
            REPO_ROOT, "scripts", "windows", "runner", "run-verified.ps1"
        ),
        "platform": "windows",
        "purpose": "verified-runner",
    },
]


def build_manifest():
    scripts = []
    for artifact in SCRIPT_ARTIFACTS:
        content = processed_content(artifact["path"])
        scripts.append(
            {
                "name": artifact["name"],
                "path": f"/v/{ARTIFACT_VERSION}/{artifact['name']}",
                "latestPath": f"/{artifact['name']}",
                "platform": artifact["platform"],
                "purpose": artifact["purpose"],
                "bytes": len(content.encode("utf-8")),
                "sha256": sha256_text(content),
            }
        )

    return {
        "schemaVersion": 1,
        "artifactVersion": ARTIFACT_VERSION,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "baseUrl": BASE_URL,
        "scripts": scripts,
        "signing": {
            "status": "unsigned",
            "note": "SHA256 verification is implemented. Authenticode signing is required before real production use.",
        },
    }

template = read_text(os.path.join(WORKER_DIR, "index.js"))

output = template
for artifact in SCRIPT_ARTIFACTS:
    output = output.replace(
        "{{" + artifact["placeholder"] + "}}",
        js_template_literal(processed_content(artifact["path"])),
    )

manifest_json = json.dumps(build_manifest(), indent=2, sort_keys=True)
output = output.replace("{{SCRIPT_MANIFEST_JSON}}", js_template_literal(manifest_json))
output = output.replace("{{ARTIFACT_VERSION}}", ARTIFACT_VERSION)

output_path = os.path.join(WORKER_DIR, "index.deploy.js")
with open(output_path, "w") as f:
    f.write(output)

print(f"Built worker: {output_path} ({len(output)} bytes)")

with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as tmp:
    tmp.write(output)
    tmp_path = tmp.name

try:
    result = subprocess.run(
        ["node", "--check", tmp_path], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(
            f"WARNING: JavaScript syntax check failed: {result.stderr}",
            file=sys.stderr,
        )
    else:
        print("JavaScript syntax: OK")
finally:
    os.unlink(tmp_path)
