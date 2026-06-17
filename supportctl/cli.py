from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from . import __version__


SCHEMA_VERSION = "2026-05-18"
DEFAULT_ACTOR = "operator:local"
DEFAULT_SUPPORT_USER = "zenux-support"
DEFAULT_IDENTITY_FILE = str(Path.home() / ".ssh" / "zenux_support_ed25519")
DEFAULT_MANIFEST_URL = "https://support.example.com/manifest.json"
DEFAULT_RUNNER_URL = "https://support.example.com/run-verified.ps1"
DEFAULT_REDACTION_PROFILE = "support-diagnostics-default"
DEFAULT_AUTHORIZED_CONTACT = "authorized-contact:pending"

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)\b("
    r"CLOUDFLARE_API_TOKEN|"
    r"TAILSCALE_AUTH_KEY|"
    r"TAILSCALE_API_KEY|"
    r"REMOTE_SUPPORT_[A-Z0-9_]*TOKEN|"
    r"SSH_AUTHORIZED_KEY|"
    r"ZENUX_SUPPORT_SSH_AUTHORIZED_KEY"
    r")\s*[:=]\s*[^\s;]+"
)
TAILSCALE_KEY_RE = re.compile(r"\btskey-[A-Za-z0-9_-]+")
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


@dataclass(frozen=True)
class CliResult:
    action: str
    command: list[str] | str
    summary: str
    warnings: list[str]
    zenux_mapping: dict[str, str]
    contract_events: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] | None = None
    command_ref: str | None = None
    execution_adapter: str | None = None
    approval_ref_suffix: str | None = None
    billing_usage_plan: BillingUsagePlan | None = None
    redaction_profile: str = DEFAULT_REDACTION_PROFILE
    exit_code: int = 0


@dataclass(frozen=True)
class BillingUsagePlan:
    usage_ref: str
    unit_type: str
    funding_requirement: str
    evidence_refs: tuple[str, ...] = ()
    artifact_class: str | None = None


ARTIFACT_POLICIES: dict[str, dict[str, Any]] = {
    "contract-event": {
        "defaultRetentionDays": 365,
        "maxRetentionDays": 365,
        "requiresApproval": False,
        "requiresConsent": False,
        "requiresSensitiveException": False,
        "uploadAllowed": True,
    },
    "command-stdout": {
        "defaultRetentionDays": 30,
        "maxRetentionDays": 30,
        "requiresApproval": False,
        "requiresConsent": False,
        "requiresSensitiveException": False,
        "uploadAllowed": True,
    },
    "command-stderr": {
        "defaultRetentionDays": 30,
        "maxRetentionDays": 30,
        "requiresApproval": False,
        "requiresConsent": False,
        "requiresSensitiveException": False,
        "uploadAllowed": True,
    },
    "diagnostic-summary": {
        "defaultRetentionDays": 90,
        "maxRetentionDays": 90,
        "requiresApproval": False,
        "requiresConsent": False,
        "requiresSensitiveException": False,
        "uploadAllowed": True,
    },
    "diagnostic-bundle": {
        "defaultRetentionDays": 30,
        "maxRetentionDays": 30,
        "requiresApproval": True,
        "requiresConsent": True,
        "requiresSensitiveException": False,
        "uploadAllowed": True,
    },
    "minidump": {
        "defaultRetentionDays": 7,
        "maxRetentionDays": 7,
        "requiresApproval": True,
        "requiresConsent": True,
        "requiresSensitiveException": True,
        "uploadAllowed": True,
    },
    "screenshot": {
        "defaultRetentionDays": 7,
        "maxRetentionDays": 7,
        "requiresApproval": True,
        "requiresConsent": True,
        "requiresSensitiveException": True,
        "uploadAllowed": True,
    },
    "customer-file": {
        "defaultRetentionDays": 7,
        "maxRetentionDays": 7,
        "requiresApproval": True,
        "requiresConsent": True,
        "requiresSensitiveException": True,
        "uploadAllowed": True,
    },
    "session-recording": {
        "defaultRetentionDays": 30,
        "maxRetentionDays": 30,
        "requiresApproval": True,
        "requiresConsent": True,
        "requiresSensitiveException": True,
        "uploadAllowed": True,
    },
    "secret": {
        "defaultRetentionDays": 0,
        "maxRetentionDays": 0,
        "requiresApproval": False,
        "requiresConsent": False,
        "requiresSensitiveException": False,
        "uploadAllowed": False,
    },
    "private-key": {
        "defaultRetentionDays": 0,
        "maxRetentionDays": 0,
        "requiresApproval": False,
        "requiresConsent": False,
        "requiresSensitiveException": False,
        "uploadAllowed": False,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_expires_at() -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=4)
    return expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return slug or "unknown"


def redacted_secret_assignment(match: re.Match[str]) -> str:
    return f"{match.group(1)}=[REDACTED:SECRET]"


def redact_output(value: str) -> tuple[str, int]:
    redacted = value
    redactions = 0
    for pattern, replacement in (
        (PRIVATE_KEY_RE, "[REDACTED:PRIVATE_KEY]"),
        (SECRET_ASSIGNMENT_RE, redacted_secret_assignment),
        (TAILSCALE_KEY_RE, "[REDACTED:TAILSCALE_AUTH_KEY]"),
    ):
        redacted, count = pattern.subn(replacement, redacted)
        redactions += count
    return redacted, redactions


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def posix_command(command: Sequence[str]) -> str:
    return shlex.join([str(part) for part in command])


def resolve_authorized_key(args: argparse.Namespace) -> str:
    if getattr(args, "authorized_key", None):
        return args.authorized_key.strip()
    if getattr(args, "authorized_key_file", None):
        return Path(args.authorized_key_file).expanduser().read_text(encoding="utf-8").strip()
    return "<ssh-public-key>"


def context_value(args: argparse.Namespace, name: str, fallback: str) -> str:
    value = getattr(args, name, None)
    return str(value) if value else fallback


def tenant_id(args: argparse.Namespace) -> str:
    return context_value(args, "tenant", "<tenant>")


def ticket_id(args: argparse.Namespace) -> str:
    return context_value(args, "ticket", "<ticket>")


def customer_id(args: argparse.Namespace) -> str:
    return context_value(args, "customer_id", tenant_id(args))


def actor_ref(args: argparse.Namespace) -> str:
    return context_value(args, "actor", DEFAULT_ACTOR)


def operator_id(args: argparse.Namespace) -> str:
    return context_value(args, "operator_id", actor_ref(args))


def authorized_contact_id(args: argparse.Namespace) -> str:
    return context_value(args, "authorized_contact_id", DEFAULT_AUTHORIZED_CONTACT)


def host_id(args: argparse.Namespace) -> str:
    return context_value(args, "hostname", context_value(args, "host", "<device>"))


def device_ref(args: argparse.Namespace) -> str:
    return f"device:{tenant_id(args)}:{host_id(args)}"


def access_session_id(args: argparse.Namespace) -> str:
    return f"support-access:{tenant_id(args)}:{ticket_id(args)}:{host_id(args)}"


def access_request_id(args: argparse.Namespace) -> str:
    return f"support-access-request:{tenant_id(args)}:{ticket_id(args)}:{host_id(args)}"


def evidence_ref(args: argparse.Namespace, suffix: str) -> str:
    return f"evidence:{tenant_id(args)}:{ticket_id(args)}:{host_id(args)}:{suffix}"


def consent_ref(args: argparse.Namespace) -> str:
    return f"consent:{tenant_id(args)}:{ticket_id(args)}:session"


def approval_ref(args: argparse.Namespace, suffix: str) -> str:
    return f"approval:{tenant_id(args)}:{ticket_id(args)}:{suffix}"


def policy_ref(args: argparse.Namespace, suffix: str) -> str:
    return f"policy:{tenant_id(args)}:{ticket_id(args)}:{suffix}"


def expiry(args: argparse.Namespace) -> str:
    return context_value(args, "expires_at", default_expires_at())


def canonical_billing_account_id(args: argparse.Namespace) -> str:
    return f"org:{customer_id(args)}"


def canonical_runtime_wallet_id(args: argparse.Namespace) -> str:
    return f"{canonical_billing_account_id(args)}:runtime"


def monthly_statement_group_ref(args: argparse.Namespace) -> str:
    return f"statement-group:support:{customer_id(args)}:{ticket_id(args)}"


def support_billing_planned_event_id(args: argparse.Namespace, usage_ref: str) -> str:
    return f"support-billing:{tenant_id(args)}:{ticket_id(args)}:{host_id(args)}:{usage_ref}"


def support_billing_usage_planned_event(
    args: argparse.Namespace,
    *,
    usage_ref: str,
    unit_type: str,
    funding_requirement: str,
    evidence_refs: Sequence[str] = (),
    artifact_class: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "eventType": "support.billing.usage_planned",
        "eventId": support_billing_planned_event_id(args, usage_ref),
        "ticketId": ticket_id(args),
        "tenantId": tenant_id(args),
        "customerId": customer_id(args),
        "billingAccountId": canonical_billing_account_id(args),
        "runtimeWalletId": canonical_runtime_wallet_id(args),
        "packageKey": "support-desk",
        "statementGroupRef": monthly_statement_group_ref(args),
        "fundingRequirement": funding_requirement,
        "unitType": unit_type,
        "unitCount": 1,
        "artifactClass": artifact_class,
        "evidenceRefs": list(evidence_refs),
        "createdAt": utc_now(),
        "status": "planned",
    }


def support_billing_usage_recorded_event(
    args: argparse.Namespace,
    plan: BillingUsagePlan,
    result: CliResult,
    *,
    started_at: str,
    finished_at: str,
    exit_code: int,
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    status = "succeeded" if exit_code == 0 else "failed"
    event_ref = (
        f"support-billing-recorded:{tenant_id(args)}:{ticket_id(args)}:{host_id(args)}:{plan.usage_ref}:{safe_slug(started_at)}"
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "eventType": "support.billing.usage_recorded",
        "eventId": event_ref,
        "plannedEventId": support_billing_planned_event_id(args, plan.usage_ref),
        "ticketId": ticket_id(args),
        "tenantId": tenant_id(args),
        "customerId": customer_id(args),
        "billingAccountId": canonical_billing_account_id(args),
        "runtimeWalletId": canonical_runtime_wallet_id(args),
        "packageKey": "support-desk",
        "statementGroupRef": monthly_statement_group_ref(args),
        "fundingRequirement": plan.funding_requirement,
        "unitType": plan.unit_type,
        "unitCount": 1,
        "artifactClass": plan.artifact_class,
        "evidenceRefs": list(evidence_refs),
        "commandRef": result.command_ref,
        "executionAdapter": result.execution_adapter,
        "approvalRef": approval_ref(args, result.approval_ref_suffix or "execution"),
        "startedAt": started_at,
        "finishedAt": finished_at,
        "exitCode": exit_code,
        "createdAt": finished_at,
        "status": status,
    }


def support_access_requested_event(
    args: argparse.Namespace,
    *,
    purpose: str,
    transports: list[str],
    commands: list[str],
    interactive_desktop: bool = False,
) -> dict[str, Any]:
    requested_access = [*transports, *commands]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "eventType": "support.access.requested",
        "requestId": access_request_id(args),
        "ticketId": ticket_id(args),
        "customerId": customer_id(args),
        "authorizedContactId": authorized_contact_id(args),
        "operatorId": operator_id(args),
        "deviceRef": device_ref(args),
        "purpose": purpose,
        "requestedAccess": requested_access,
        "expiresAt": expiry(args),
        "approvalRef": approval_ref(args, "access"),
        "consentRef": consent_ref(args),
        "preferredProvider": "tailscale" if "tailscale" in transports else None,
        "constraints": {
            "commands": commands,
            "fileAccess": "diagnostic-output-only",
            "interactiveDesktop": interactive_desktop,
            "customerVisible": True,
            "noPublicExposure": True,
        },
        "metadata": {
            "tenantId": tenant_id(args),
            "os": "windows",
            "requestedTransports": transports,
            "evidenceSinkRef": f"evidence:{tenant_id(args)}:{ticket_id(args)}",
        },
        "createdAt": utc_now(),
        "status": "planned",
    }


def support_command_approval_requested_event(args: argparse.Namespace, *, command_ref: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "eventType": "support.command.approval_requested",
        "eventId": f"support-command-approval:{tenant_id(args)}:{ticket_id(args)}:{host_id(args)}:{command_ref}",
        "ticketId": ticket_id(args),
        "tenantId": tenant_id(args),
        "customerId": customer_id(args),
        "accessSessionId": access_session_id(args),
        "operatorId": operator_id(args),
        "executionAdapter": "windows-openssh",
        "commandRef": command_ref,
        "approvalRef": approval_ref(args, "diagnostics-read"),
        "requestedAt": utc_now(),
        "riskLevel": "read-only",
        "redactionProfile": DEFAULT_REDACTION_PROFILE,
        "evidenceRefs": [evidence_ref(args, "approval-requested")],
        "policyDecisionRef": policy_ref(args, "diagnostics-read"),
        "status": "planned",
    }


def support_command_executed_event(
    args: argparse.Namespace,
    result: CliResult,
    *,
    started_at: str,
    finished_at: str,
    exit_code: int,
    stdout_path: Path,
    stderr_path: Path,
    stdout_redactions: int,
    stderr_redactions: int,
) -> dict[str, Any]:
    command_ref = result.command_ref or result.action
    stdout_ref = evidence_ref(args, f"{command_ref}:stdout")
    stderr_ref = evidence_ref(args, f"{command_ref}:stderr")
    event_ref = f"support-command-executed:{tenant_id(args)}:{ticket_id(args)}:{host_id(args)}:{command_ref}"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "eventType": "support.command.executed",
        "eventId": event_ref,
        "ticketId": ticket_id(args),
        "tenantId": tenant_id(args),
        "customerId": customer_id(args),
        "accessSessionId": access_session_id(args),
        "operatorId": operator_id(args),
        "executionAdapter": result.execution_adapter or "unknown",
        "commandRef": command_ref,
        "approvalRef": approval_ref(args, result.approval_ref_suffix or "execution"),
        "startedAt": started_at,
        "finishedAt": finished_at,
        "exitCode": exit_code,
        "stdoutRef": stdout_ref,
        "stderrRef": stderr_ref,
        "redactionProfile": result.redaction_profile,
        "redactionSummary": {
            "stdoutRedactions": stdout_redactions,
            "stderrRedactions": stderr_redactions,
        },
        "evidenceRefs": [stdout_ref, stderr_ref, evidence_ref(args, f"{command_ref}:executed")],
        "localArtifacts": {
            "stdoutPath": str(stdout_path),
            "stderrPath": str(stderr_path),
        },
    }


def support_access_revoke_requested_event(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "eventType": "support.access.revoke_requested",
        "requestId": f"support-access-revoke-request:{tenant_id(args)}:{ticket_id(args)}:{host_id(args)}",
        "ticketId": ticket_id(args),
        "accessId": access_session_id(args),
        "operatorId": operator_id(args),
        "reason": "ticket-closed",
        "metadata": {
            "tenantId": tenant_id(args),
            "customerId": customer_id(args),
            "deviceRef": device_ref(args),
            "requestedAt": utc_now(),
            "revocationRef": f"revoke:{access_session_id(args)}",
            "evidenceRefs": [evidence_ref(args, "offboarding-requested")],
        },
        "status": "planned",
    }


def base_mapping(args: argparse.Namespace) -> dict[str, str]:
    tenant = tenant_id(args)
    ticket = ticket_id(args)
    hostname = host_id(args)
    return {
        "asset": f"device:{tenant}:{hostname}",
        "case": f"support-ticket:{tenant}:{ticket}",
        "approval": f"support-access:{tenant}:{ticket}",
        "playbook": "zenux-support.windows",
        "evidence": f"support-evidence:{tenant}:{ticket}:{hostname}",
        "audit": f"support-session:{tenant}:{ticket}:{hostname}",
        "billingAccount": canonical_billing_account_id(args),
        "runtimeWallet": canonical_runtime_wallet_id(args),
        "statementGroup": monthly_statement_group_ref(args),
    }


def build_key_create(args: argparse.Namespace) -> CliResult:
    command = (
        "Submit the emitted support.access.requested event to ZenuxLabs/networking; "
        "this support repo does not create Tailscale or provider keys."
    )
    return CliResult(
        action="key.create",
        command=command,
        summary="Plan a ticket-scoped private access bootstrap key request.",
        warnings=[
            "Networking owns real Tailscale/provider key creation and revocation.",
            "Support must not store or print auth keys in contract payloads.",
            "Use one-off, short-lived keys and record the networking access id on the ticket.",
        ],
        zenux_mapping=base_mapping(args),
        contract_events=(
            support_access_requested_event(
                args,
                purpose="create ticket-scoped private access bootstrap key",
                transports=["tailscale"],
                commands=["networking.key.create"],
            ),
            support_billing_usage_planned_event(
                args,
                usage_ref="key-create",
                unit_type="support_access_request",
                funding_requirement="entitlement_only",
            ),
        ),
    )


def build_bootstrap_windows(args: argparse.Namespace) -> CliResult:
    command = "; ".join(
        [
            f"$env:TAILSCALE_AUTH_KEY = {ps_quote(args.auth_key)}",
            f"$env:ZENUX_SUPPORT_TICKET_ID = {ps_quote(args.ticket)}",
            f"$env:ZENUX_SUPPORT_HOSTNAME = {ps_quote(args.hostname)}",
            f"$env:ZENUX_SUPPORT_SSH_AUTHORIZED_KEY = {ps_quote(resolve_authorized_key(args))}",
            f"$env:ZENUX_SUPPORT_SSH_USER = {ps_quote(args.support_user)}",
            "$runner = Join-Path $env:TEMP 'zenux-run-verified.ps1'",
            f"Invoke-WebRequest -Uri {ps_quote(args.runner_url)} -OutFile $runner",
            "powershell -NoProfile -ExecutionPolicy Bypass -File $runner "
            f"-ManifestUrl {ps_quote(args.manifest_url)} "
            "-Script 'customer-ssh-bootstrap.ps1'",
            "Remove-Item $runner -Force",
        ]
    )
    return CliResult(
        action="bootstrap.windows",
        command=command,
        summary="Customer-side elevated PowerShell bootstrap for Tailscale plus Windows OpenSSH.",
        warnings=[
            "The target support script is hash-verified through manifest.json.",
            "The downloaded runner still needs signing or pinned delivery before real production use.",
            "Run only in a customer-visible support session with recorded consent.",
        ],
        zenux_mapping=base_mapping(args),
        contract_events=(
            support_access_requested_event(
                args,
                purpose="bootstrap customer endpoint with Tailscale plus Windows OpenSSH",
                transports=["tailscale", "ssh"],
                commands=["bootstrap.windows", "ssh.enable"],
            ),
            support_billing_usage_planned_event(
                args,
                usage_ref="bootstrap-windows",
                unit_type="support_session_bootstrap",
                funding_requirement="entitlement_only",
            ),
        ),
    )


def ssh_base(args: argparse.Namespace) -> list[str]:
    return [
        "ssh",
        "-i",
        args.identity_file,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{args.user}@{args.host}",
    ]


def build_ssh_windows(args: argparse.Namespace) -> CliResult:
    command = ssh_base(args)
    if args.remote_command:
        command.extend(args.remote_command)
    return CliResult(
        action="ssh.windows",
        command=command,
        summary="Open a Windows OpenSSH session over private transport.",
        warnings=[
            "Windows OpenSSH must be reachable only over private transport.",
            "Interactive shell access should stay ticket-scoped and time-bound.",
        ],
        zenux_mapping=base_mapping(args),
    )


def remote_runner_command(args: argparse.Namespace, script_name: str, script_args: list[str] | None = None) -> list[str]:
    pieces = []
    if getattr(args, "ticket", None):
        pieces.append(f"$env:ZENUX_SUPPORT_TICKET_ID = {ps_quote(args.ticket)}")
    if getattr(args, "user", None):
        pieces.append(f"$env:ZENUX_SUPPORT_SSH_USER = {ps_quote(args.user)}")
    pieces.extend(
        [
            "$runner = Join-Path $env:TEMP 'zenux-run-verified.ps1'",
            f"Invoke-WebRequest -Uri {ps_quote(args.runner_url)} -OutFile $runner",
        ]
    )
    runner_args = [
        "powershell -NoProfile -ExecutionPolicy Bypass -File $runner",
        f"-ManifestUrl {ps_quote(args.manifest_url)}",
        f"-Script {ps_quote(script_name)}",
    ]
    if script_args:
        quoted_args = ", ".join(ps_quote(value) for value in script_args)
        runner_args.append(f"-ScriptArgs @({quoted_args})")
    pieces.append(" ".join(runner_args))
    pieces.append("Remove-Item $runner -Force")
    remote = "; ".join(pieces)
    return ssh_base(args) + ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", remote]


def build_diag_windows(args: argparse.Namespace) -> CliResult:
    command_ref = "diag.windows.crash-check"
    command = remote_runner_command(args, "crash-check.ps1")
    return CliResult(
        action="diag.windows",
        command=command,
        summary="Run the Windows crash/log diagnostic collector over SSH.",
        warnings=[
            "The target diagnostic script is hash-verified through manifest.json.",
            "The downloaded runner still needs signing or pinned delivery before real production use.",
            "Upload or retain diagnostic output only under the approved ticket policy.",
        ],
        zenux_mapping=base_mapping(args),
        contract_events=(
            support_command_approval_requested_event(args, command_ref=command_ref),
            support_billing_usage_planned_event(
                args,
                usage_ref=command_ref,
                unit_type="support_diagnostic_run",
                funding_requirement="runtime_wallet_required",
                evidence_refs=[evidence_ref(args, "approval-requested")],
            ),
        ),
        command_ref=command_ref,
        execution_adapter="windows-openssh",
        approval_ref_suffix="diagnostics-read",
        billing_usage_plan=BillingUsagePlan(
            usage_ref=command_ref,
            unit_type="support_diagnostic_run",
            funding_requirement="runtime_wallet_required",
            evidence_refs=(evidence_ref(args, "approval-requested"),),
        ),
    )


def build_offboard_windows(args: argparse.Namespace) -> CliResult:
    extra_flags = []
    if args.stop_sshd:
        extra_flags.append("-StopSshd")
    if args.disable_sshd:
        extra_flags.append("-DisableSshd")

    command = remote_runner_command(args, "windows-ssh-offboard.ps1", extra_flags)

    return CliResult(
        action="offboard.windows",
        command=command,
        summary="Remove temporary Windows SSH support access.",
        warnings=[
            "Offboarding evidence should be attached before support ticket closure.",
            "Confirm the Tailscale device/key lifecycle separately until API offboarding is implemented.",
        ],
        zenux_mapping=base_mapping(args),
        contract_events=(
            support_access_revoke_requested_event(args),
            support_billing_usage_planned_event(
                args,
                usage_ref="offboard-windows",
                unit_type="support_offboarding_run",
                funding_requirement="runtime_wallet_required",
                evidence_refs=[evidence_ref(args, "offboarding-requested")],
            ),
        ),
        billing_usage_plan=BillingUsagePlan(
            usage_ref="offboard-windows",
            unit_type="support_offboarding_run",
            funding_requirement="runtime_wallet_required",
            evidence_refs=(evidence_ref(args, "offboarding-requested"),),
        ),
    )


def artifact_redaction_findings(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    sample = path.read_bytes()[:1024 * 1024].decode("utf-8", errors="ignore")
    _, findings = redact_output(sample)
    return findings


def evidence_upload_policy(args: argparse.Namespace) -> dict[str, Any]:
    policy = ARTIFACT_POLICIES[args.artifact_class]
    artifact_path = Path(args.path).expanduser()
    retention_days = args.retention_days if args.retention_days is not None else policy["defaultRetentionDays"]
    missing_refs = []
    reasons = []
    redaction_findings = artifact_redaction_findings(artifact_path)

    if not artifact_path.exists():
        reasons.append("artifact path does not exist")
    if not policy["uploadAllowed"]:
        reasons.append("artifact class is never uploadable")
    if redaction_findings:
        reasons.append("artifact appears to contain unredacted secrets")
    if policy["requiresApproval"] and not args.approval_ref:
        missing_refs.append("approvalRef")
    if policy["requiresConsent"] and not args.consent_ref:
        missing_refs.append("consentRef")
    if policy["requiresSensitiveException"] and not args.sensitive_exception_ref:
        missing_refs.append("sensitiveExceptionRef")
    if missing_refs:
        reasons.append("missing required refs: " + ", ".join(missing_refs))
    if retention_days > policy["maxRetentionDays"]:
        reasons.append(f"retention exceeds max {policy['maxRetentionDays']} days")

    decision = "refuse" if reasons else "allow"
    return {
        "artifactPath": str(artifact_path),
        "artifactExists": artifact_path.exists(),
        "artifactClass": args.artifact_class,
        "uploadDecision": decision,
        "reasons": reasons,
        "requiredRefs": {
            "approvalRef": policy["requiresApproval"],
            "consentRef": policy["requiresConsent"],
            "sensitiveExceptionRef": policy["requiresSensitiveException"],
        },
        "approvalRef": args.approval_ref,
        "consentRef": args.consent_ref,
        "sensitiveExceptionRef": args.sensitive_exception_ref,
        "retentionDays": retention_days if decision == "allow" else None,
        "maxRetentionDays": policy["maxRetentionDays"],
        "redactionFindings": redaction_findings,
        "deleteLocalAfterUpload": decision == "allow",
        "evidenceRef": evidence_ref(args, f"upload:{args.artifact_class}"),
        "policyRef": policy_ref(args, "evidence-upload"),
        "billingStatementAttachment": {
            "billingAccountId": canonical_billing_account_id(args),
            "runtimeWalletId": canonical_runtime_wallet_id(args),
            "statementGroupRef": monthly_statement_group_ref(args),
            "packageKey": "support-desk",
            "lineItemType": "support_evidence_retention_item",
            "artifactClass": args.artifact_class,
        },
        "note": "No upload is performed by this command.",
    }


def build_evidence_plan_upload(args: argparse.Namespace) -> CliResult:
    decision = evidence_upload_policy(args)
    warnings = [
        "This command plans evidence upload only; it does not upload artifacts.",
        "Actual upload must preserve evidence refs and use the approved Zenux evidence sink.",
    ]
    if decision["uploadDecision"] == "refuse":
        warnings.extend(decision["reasons"])

    return CliResult(
        action="evidence.plan-upload",
        command="No upload performed. Policy decision only.",
        summary=f"Plan evidence upload for {args.artifact_class}: {decision['uploadDecision']}.",
        warnings=warnings,
        zenux_mapping=base_mapping(args),
        metadata={"evidenceUploadPlan": decision},
        exit_code=0 if decision["uploadDecision"] == "allow" else 2,
    )


def result_payload(result: CliResult, evidence_files: list[Path] | None = None) -> dict[str, Any]:
    payload = {
        "action": result.action,
        "summary": result.summary,
        "command": result.command if isinstance(result.command, str) else posix_command(result.command),
        "argv": result.command if isinstance(result.command, list) else None,
        "warnings": result.warnings,
        "zenuxMapping": result.zenux_mapping,
        "contractEvents": result.contract_events,
    }
    if result.metadata is not None:
        payload.update(result.metadata)
    if evidence_files is not None:
        payload["evidenceFiles"] = [str(path) for path in evidence_files]
    return payload


def write_evidence_files(result: CliResult, evidence_dir: str | None) -> list[Path]:
    if not evidence_dir or not result.contract_events:
        return []

    output_dir = Path(evidence_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().replace("-", "").replace(":", "").replace("T", "-").replace("Z", "")

    paths: list[Path] = []
    for event in result.contract_events:
        event_type = safe_slug(str(event["eventType"]))
        event_ref = safe_slug(
            str(
                event.get("eventId")
                or event.get("requestId")
                or event.get("accessSessionId")
                or result.action
            )
        )
        path = output_dir / f"{timestamp}-{event_type}-{event_ref}.json"
        path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def evidence_output_path(output_dir: Path, event: dict[str, Any], suffix: str = "json") -> Path:
    timestamp = utc_now().replace("-", "").replace(":", "").replace("T", "-").replace("Z", "")
    event_type = safe_slug(str(event["eventType"]))
    event_ref = safe_slug(
        str(
            event.get("eventId")
            or event.get("requestId")
            or event.get("accessSessionId")
            or event_type
        )
    )
    return output_dir / f"{timestamp}-{event_type}-{event_ref}.{suffix}"


def write_execution_evidence(
    result: CliResult,
    args: argparse.Namespace,
    completed: subprocess.CompletedProcess[str],
    started_at: str,
    finished_at: str,
    evidence_dir: str,
) -> list[Path]:
    if not result.command_ref:
        return []

    output_dir = Path(evidence_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    command_ref = safe_slug(result.command_ref)
    run_stamp = started_at.replace("-", "").replace(":", "").replace("T", "-").replace("Z", "")
    artifact_prefix = f"{run_stamp}-{safe_slug(ticket_id(args))}-{safe_slug(host_id(args))}-{command_ref}"
    stdout_path = output_dir / f"{artifact_prefix}-stdout.txt"
    stderr_path = output_dir / f"{artifact_prefix}-stderr.txt"

    stdout_redacted, stdout_redactions = redact_output(completed.stdout or "")
    stderr_redacted, stderr_redactions = redact_output(completed.stderr or "")
    stdout_path.write_text(stdout_redacted, encoding="utf-8")
    stderr_path.write_text(stderr_redacted, encoding="utf-8")

    event = support_command_executed_event(
        args,
        result,
        started_at=started_at,
        finished_at=finished_at,
        exit_code=completed.returncode,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        stdout_redactions=stdout_redactions,
        stderr_redactions=stderr_redactions,
    )
    event_path = evidence_output_path(output_dir, event)
    event_path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = [stdout_path, stderr_path, event_path]

    if result.billing_usage_plan is not None:
        billing_event = support_billing_usage_recorded_event(
            args,
            result.billing_usage_plan,
            result,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=completed.returncode,
            evidence_refs=[
                *result.billing_usage_plan.evidence_refs,
                *event["evidenceRefs"],
            ],
        )
        billing_event_path = evidence_output_path(output_dir, billing_event)
        billing_event_path.write_text(json.dumps(billing_event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(billing_event_path)

    return paths


def print_result(result: CliResult, output_format: str, evidence_files: list[Path] | None = None) -> None:
    payload = result_payload(result, evidence_files)
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print(result.summary)
    print()
    print(payload["command"])
    if result.warnings:
        print()
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    if evidence_files:
        print()
        print("Evidence files:")
        for path in evidence_files:
            print(f"- {path}")


def execute_result(result: CliResult, args: argparse.Namespace) -> int:
    if isinstance(result.command, str):
        print(result.command)
        print("This command must be run from an elevated customer PowerShell session.", file=sys.stderr)
        return 2

    evidence_dir = getattr(args, "evidence_dir", None)
    if not evidence_dir or not result.command_ref:
        completed = subprocess.run(result.command)
        return completed.returncode

    started_at = utc_now()
    completed = subprocess.run(result.command, text=True, capture_output=True)
    finished_at = utc_now()

    stdout_redacted, _ = redact_output(completed.stdout or "")
    stderr_redacted, _ = redact_output(completed.stderr or "")
    if stdout_redacted:
        print(stdout_redacted, end="")
    if stderr_redacted:
        print(stderr_redacted, end="", file=sys.stderr)

    for path in write_execution_evidence(result, args, completed, started_at, finished_at, evidence_dir):
        print(f"Wrote evidence: {path}", file=sys.stderr)
    return completed.returncode


def add_common_ticket_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tenant", required=True, help="Tenant slug, for example acme.")
    parser.add_argument("--ticket", required=True, help="Support ticket ID.")


def add_optional_ticket_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tenant", help="Tenant slug, for example acme.")
    parser.add_argument("--ticket", help="Support ticket ID.")


def add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["text", "json"], default="text")


def add_contract_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--actor", default=DEFAULT_ACTOR, help="Actor ref recorded in local contract evidence.")
    parser.add_argument("--operator-id", help="Named support engineer or automation actor. Defaults to --actor.")
    parser.add_argument(
        "--authorized-contact-id",
        help="Verified customer contact approving the session. Defaults to pending placeholder.",
    )
    parser.add_argument("--customer-id", help="Customer ref recorded in local contract evidence. Defaults to tenant.")
    parser.add_argument("--expires-at", help="Temporary access expiry timestamp. Defaults to four hours from now.")
    parser.add_argument("--evidence-dir", help="Write planned contract evidence JSON files to this directory.")


def add_ssh_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", required=True, help="Private hostname or Tailscale IP.")
    parser.add_argument("--user", default=DEFAULT_SUPPORT_USER)
    parser.add_argument("--identity-file", default=DEFAULT_IDENTITY_FILE)
    parser.add_argument("--execute", action="store_true", help="Run the SSH command locally.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="supportctl",
        description="Thin operator CLI for the remote support fabric.",
    )
    parser.add_argument("--version", action="version", version=f"supportctl {__version__}")

    subparsers = parser.add_subparsers(dest="area", required=True)

    key = subparsers.add_parser("key", help="Private access key request helpers.")
    key_sub = key.add_subparsers(dest="command", required=True)
    key_create = key_sub.add_parser("create", help="Plan a networking-owned ticket-scoped key request.")
    add_common_ticket_args(key_create)
    key_create.add_argument("--hostname")
    add_output_args(key_create)
    add_contract_args(key_create)
    key_create.set_defaults(builder=build_key_create)

    bootstrap = subparsers.add_parser("bootstrap", help="Customer bootstrap helpers.")
    bootstrap_sub = bootstrap.add_subparsers(dest="os", required=True)
    bootstrap_windows = bootstrap_sub.add_parser("windows", help="Print a Windows bootstrap command.")
    add_common_ticket_args(bootstrap_windows)
    bootstrap_windows.add_argument("--hostname", required=True)
    bootstrap_windows.add_argument("--auth-key", default="<tailscale-auth-key>")
    bootstrap_windows.add_argument("--authorized-key")
    bootstrap_windows.add_argument("--authorized-key-file")
    bootstrap_windows.add_argument("--support-user", default=DEFAULT_SUPPORT_USER)
    bootstrap_windows.add_argument("--manifest-url", default=DEFAULT_MANIFEST_URL)
    bootstrap_windows.add_argument("--runner-url", default=DEFAULT_RUNNER_URL)
    add_output_args(bootstrap_windows)
    add_contract_args(bootstrap_windows)
    bootstrap_windows.set_defaults(builder=build_bootstrap_windows)

    ssh = subparsers.add_parser("ssh", help="SSH session helpers.")
    ssh_sub = ssh.add_subparsers(dest="os", required=True)
    ssh_windows = ssh_sub.add_parser("windows", help="Print or run a Windows SSH command.")
    add_optional_ticket_args(ssh_windows)
    add_ssh_args(ssh_windows)
    ssh_windows.add_argument("remote_command", nargs=argparse.REMAINDER)
    add_output_args(ssh_windows)
    add_contract_args(ssh_windows)
    ssh_windows.set_defaults(builder=build_ssh_windows)

    diag = subparsers.add_parser("diag", help="Diagnostic helpers.")
    diag_sub = diag.add_subparsers(dest="os", required=True)
    diag_windows = diag_sub.add_parser("windows", help="Print or run Windows diagnostics over SSH.")
    add_common_ticket_args(diag_windows)
    add_ssh_args(diag_windows)
    diag_windows.add_argument("--manifest-url", default=DEFAULT_MANIFEST_URL)
    diag_windows.add_argument("--runner-url", default=DEFAULT_RUNNER_URL)
    add_output_args(diag_windows)
    add_contract_args(diag_windows)
    diag_windows.set_defaults(builder=build_diag_windows)

    offboard = subparsers.add_parser("offboard", help="Offboarding helpers.")
    offboard_sub = offboard.add_subparsers(dest="os", required=True)
    offboard_windows = offboard_sub.add_parser("windows", help="Print or run Windows SSH offboarding over SSH.")
    add_common_ticket_args(offboard_windows)
    add_ssh_args(offboard_windows)
    offboard_windows.add_argument("--manifest-url", default=DEFAULT_MANIFEST_URL)
    offboard_windows.add_argument("--runner-url", default=DEFAULT_RUNNER_URL)
    offboard_windows.add_argument("--stop-sshd", action="store_true")
    offboard_windows.add_argument("--disable-sshd", action="store_true")
    add_output_args(offboard_windows)
    add_contract_args(offboard_windows)
    offboard_windows.set_defaults(builder=build_offboard_windows)

    evidence = subparsers.add_parser("evidence", help="Evidence policy helpers.")
    evidence_sub = evidence.add_subparsers(dest="command", required=True)
    plan_upload = evidence_sub.add_parser("plan-upload", help="Plan evidence upload policy without uploading.")
    add_common_ticket_args(plan_upload)
    plan_upload.add_argument("--host", required=True, help="Private hostname or device ref suffix.")
    plan_upload.add_argument("--path", required=True, help="Local artifact path to evaluate.")
    plan_upload.add_argument("--artifact-class", required=True, choices=sorted(ARTIFACT_POLICIES))
    plan_upload.add_argument("--approval-ref")
    plan_upload.add_argument("--consent-ref")
    plan_upload.add_argument("--sensitive-exception-ref")
    plan_upload.add_argument("--retention-days", type=int)
    add_output_args(plan_upload)
    add_contract_args(plan_upload)
    plan_upload.set_defaults(builder=build_evidence_plan_upload)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.builder(args)
    evidence_files = write_evidence_files(result, getattr(args, "evidence_dir", None))

    if getattr(args, "execute", False):
        for path in evidence_files:
            print(f"Wrote evidence: {path}", file=sys.stderr)
        return execute_result(result, args)

    print_result(result, args.format, evidence_files)
    return result.exit_code
