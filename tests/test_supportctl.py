import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from supportctl.cli import main


class SupportCtlTests(unittest.TestCase):
    def run_cli(self, *args):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(list(args))
        self.assertEqual(code, 0)
        return stdout.getvalue()

    def run_cli_with_code(self, *args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_bootstrap_windows_renders_ticket_scoped_command(self):
        output = self.run_cli(
            "bootstrap",
            "windows",
            "--tenant",
            "acme",
            "--ticket",
            "TICKET-0001",
            "--hostname",
            "host-0001",
            "--auth-key",
            "tskey-test",
            "--authorized-key",
            "ssh-ed25519 AAAA zenux-support",
        )

        self.assertIn("$env:TAILSCALE_AUTH_KEY = 'tskey-test'", output)
        self.assertIn("$env:ZENUX_SUPPORT_TICKET_ID = 'TICKET-0001'", output)
        self.assertIn("$env:ZENUX_SUPPORT_HOSTNAME = 'host-0001'", output)
        self.assertIn("https://support.example.com/run-verified.ps1", output)
        self.assertIn("-ManifestUrl 'https://support.example.com/manifest.json'", output)
        self.assertIn("-Script 'customer-ssh-bootstrap.ps1'", output)
        self.assertIn("hash-verified through manifest.json", output)

    def test_ssh_windows_json_contains_command_and_mapping(self):
        output = self.run_cli(
            "ssh",
            "windows",
            "--host",
            "host-0001",
            "--format",
            "json",
        )
        payload = json.loads(output)

        self.assertEqual(payload["action"], "ssh.windows")
        self.assertIn("zenux-support@host-0001", payload["command"])
        self.assertEqual(payload["zenuxMapping"]["asset"], "device:<tenant>:host-0001")
        self.assertEqual(payload["contractEvents"], [])

    def test_diag_windows_renders_remote_powershell(self):
        output = self.run_cli(
            "diag",
            "windows",
            "--tenant",
            "acme",
            "--ticket",
            "TICKET-0001",
            "--host",
            "host-0001",
            "--format",
            "json",
        )
        payload = json.loads(output)
        remote_command = payload["argv"][-1]

        self.assertIn("ssh", payload["argv"][0])
        self.assertIn("https://support.example.com/run-verified.ps1", remote_command)
        self.assertIn("-Script 'crash-check.ps1'", remote_command)
        self.assertIn("-ManifestUrl 'https://support.example.com/manifest.json'", remote_command)

    def test_key_create_defaults_to_printing_command(self):
        output = self.run_cli(
            "key",
            "create",
            "--tenant",
            "acme",
            "--ticket",
            "TICKET-0001",
            "--hostname",
            "host-0001",
        )

        self.assertIn("Submit the emitted support.access.requested event to ZenuxLabs/networking", output)
        self.assertIn("Networking owns real Tailscale/provider key creation and revocation.", output)
        self.assertIn("Support must not store or print auth keys in contract payloads.", output)

    def test_bootstrap_windows_json_includes_support_access_contract_event(self):
        output = self.run_cli(
            "bootstrap",
            "windows",
            "--tenant",
            "acme",
            "--ticket",
            "TICKET-0001",
            "--hostname",
            "host-0001",
            "--auth-key",
            "tskey-test",
            "--authorized-key",
            "ssh-ed25519 AAAA zenux-support",
            "--format",
            "json",
        )
        payload = json.loads(output)
        event = payload["contractEvents"][0]
        billing_event = payload["contractEvents"][1]

        self.assertEqual(event["eventType"], "support.access.requested")
        self.assertEqual(event["ticketId"], "TICKET-0001")
        self.assertEqual(event["metadata"]["tenantId"], "acme")
        self.assertEqual(event["deviceRef"], "device:acme:host-0001")
        self.assertEqual(event["requestedAccess"], ["tailscale", "ssh", "bootstrap.windows", "ssh.enable"])
        self.assertEqual(event["approvalRef"], "approval:acme:TICKET-0001:access")
        self.assertEqual(event["authorizedContactId"], "authorized-contact:pending")
        self.assertEqual(billing_event["eventType"], "support.billing.usage_planned")
        self.assertEqual(billing_event["billingAccountId"], "org:acme")
        self.assertEqual(billing_event["runtimeWalletId"], "org:acme:runtime")
        self.assertEqual(billing_event["statementGroupRef"], "statement-group:support:acme:TICKET-0001")
        self.assertEqual(billing_event["fundingRequirement"], "entitlement_only")
        self.assertEqual(billing_event["packageKey"], "support-desk")

    def test_diag_windows_writes_local_contract_evidence_file(self):
        with tempfile.TemporaryDirectory() as evidence_dir:
            output = self.run_cli(
                "diag",
                "windows",
                "--tenant",
                "acme",
                "--ticket",
                "TICKET-0001",
                "--host",
                "host-0001",
                "--evidence-dir",
                evidence_dir,
                "--format",
                "json",
            )
            payload = json.loads(output)
            evidence_files = payload["evidenceFiles"]

            self.assertEqual(len(evidence_files), 2)
            approval_files = [
                Path(path)
                for path in evidence_files
                if json.loads(Path(path).read_text(encoding="utf-8"))["eventType"]
                == "support.command.approval_requested"
            ]
            self.assertEqual(len(approval_files), 1)
            evidence_path = approval_files[0]
            self.assertTrue(evidence_path.exists())

            event = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(event["eventType"], "support.command.approval_requested")
            self.assertEqual(event["commandRef"], "diag.windows.crash-check")
            self.assertEqual(event["accessSessionId"], "support-access:acme:TICKET-0001:host-0001")
            self.assertEqual(event["policyDecisionRef"], "policy:acme:TICKET-0001:diagnostics-read")

            billing_events = [
                json.loads(Path(path).read_text(encoding="utf-8"))
                for path in evidence_files
                if json.loads(Path(path).read_text(encoding="utf-8"))["eventType"]
                == "support.billing.usage_planned"
            ]
            self.assertEqual(len(billing_events), 1)
            self.assertEqual(billing_events[0]["fundingRequirement"], "runtime_wallet_required")
            self.assertEqual(billing_events[0]["evidenceRefs"], ["evidence:acme:TICKET-0001:host-0001:approval-requested"])

    def test_diag_windows_execute_writes_executed_evidence_and_redacted_artifacts(self):
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="diagnostic ok\nTAILSCALE_AUTH_KEY=tskey-secret-value\n",
            stderr="warning token tskey-another-secret\n",
        )
        with tempfile.TemporaryDirectory() as evidence_dir:
            with patch("supportctl.cli.subprocess.run", return_value=completed) as run:
                code, stdout, stderr = self.run_cli_with_code(
                    "diag",
                    "windows",
                    "--tenant",
                    "acme",
                    "--ticket",
                    "TICKET-0001",
                    "--host",
                    "host-0001",
                    "--evidence-dir",
                    evidence_dir,
                    "--execute",
                )

            self.assertEqual(code, 0)
            run.assert_called_once()
            self.assertTrue(run.call_args.kwargs["capture_output"])
            self.assertTrue(run.call_args.kwargs["text"])
            self.assertIn("diagnostic ok", stdout)
            self.assertNotIn("tskey-secret-value", stdout)
            self.assertIn("[REDACTED:SECRET]", stdout)
            self.assertNotIn("tskey-another-secret", stderr)

            evidence_paths = sorted(Path(evidence_dir).glob("*"))
            executed_events = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in evidence_paths
                if path.name.endswith(".json")
                and json.loads(path.read_text(encoding="utf-8"))["eventType"] == "support.command.executed"
            ]
            self.assertEqual(len(executed_events), 1)
            event = executed_events[0]
            self.assertEqual(event["exitCode"], 0)
            self.assertEqual(event["commandRef"], "diag.windows.crash-check")
            self.assertEqual(event["stdoutRef"], "evidence:acme:TICKET-0001:host-0001:diag.windows.crash-check:stdout")
            self.assertEqual(event["stderrRef"], "evidence:acme:TICKET-0001:host-0001:diag.windows.crash-check:stderr")
            self.assertEqual(event["redactionSummary"]["stdoutRedactions"], 1)
            self.assertEqual(event["redactionSummary"]["stderrRedactions"], 1)

            stdout_artifact = Path(event["localArtifacts"]["stdoutPath"])
            stderr_artifact = Path(event["localArtifacts"]["stderrPath"])
            self.assertNotIn("tskey-secret-value", stdout_artifact.read_text(encoding="utf-8"))
            self.assertNotIn("tskey-another-secret", stderr_artifact.read_text(encoding="utf-8"))

            billing_events = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in evidence_paths
                if path.name.endswith(".json")
                and json.loads(path.read_text(encoding="utf-8"))["eventType"] == "support.billing.usage_recorded"
            ]
            self.assertEqual(len(billing_events), 1)
            billing_event = billing_events[0]
            self.assertEqual(billing_event["status"], "succeeded")
            self.assertEqual(billing_event["exitCode"], 0)
            self.assertEqual(
                billing_event["plannedEventId"],
                "support-billing:acme:TICKET-0001:host-0001:diag.windows.crash-check",
            )
            self.assertIn("evidence:acme:TICKET-0001:host-0001:approval-requested", billing_event["evidenceRefs"])
            self.assertIn(event["stdoutRef"], billing_event["evidenceRefs"])
            self.assertIn(event["stderrRef"], billing_event["evidenceRefs"])

    def test_diag_windows_execute_records_nonzero_exit(self):
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=7,
            stdout="",
            stderr="remote command failed\n",
        )
        with tempfile.TemporaryDirectory() as evidence_dir:
            with patch("supportctl.cli.subprocess.run", return_value=completed):
                code, _, _ = self.run_cli_with_code(
                    "diag",
                    "windows",
                    "--tenant",
                    "acme",
                    "--ticket",
                    "TICKET-0001",
                    "--host",
                    "host-0001",
                    "--evidence-dir",
                    evidence_dir,
                    "--execute",
                )

            self.assertEqual(code, 7)
            executed_events = []
            for path in Path(evidence_dir).glob("*.json"):
                event = json.loads(path.read_text(encoding="utf-8"))
                if event["eventType"] == "support.command.executed":
                    executed_events.append(event)
            self.assertEqual(len(executed_events), 1)
            self.assertEqual(executed_events[0]["exitCode"], 7)

            billing_events = []
            for path in Path(evidence_dir).glob("*.json"):
                event = json.loads(path.read_text(encoding="utf-8"))
                if event["eventType"] == "support.billing.usage_recorded":
                    billing_events.append(event)
            self.assertEqual(len(billing_events), 1)
            self.assertEqual(billing_events[0]["status"], "failed")
            self.assertEqual(billing_events[0]["exitCode"], 7)

    def test_offboard_windows_uses_verified_runner_before_passing_flags(self):
        output = self.run_cli(
            "offboard",
            "windows",
            "--tenant",
            "acme",
            "--ticket",
            "TICKET-0001",
            "--host",
            "host-0001",
            "--disable-sshd",
            "--format",
            "json",
        )
        payload = json.loads(output)
        remote_command = payload["argv"][-1]

        self.assertIn("https://support.example.com/run-verified.ps1", remote_command)
        self.assertIn("-Script 'windows-ssh-offboard.ps1'", remote_command)
        self.assertIn("-ScriptArgs @('-DisableSshd')", remote_command)
        self.assertNotIn("iex -DisableSshd", remote_command)

    def test_evidence_plan_upload_allows_redacted_command_stdout(self):
        with tempfile.NamedTemporaryFile() as artifact:
            artifact.write(b"redacted output\n")
            artifact.flush()

            output = self.run_cli(
                "evidence",
                "plan-upload",
                "--tenant",
                "acme",
                "--ticket",
                "TICKET-0001",
                "--host",
                "host-0001",
                "--path",
                artifact.name,
                "--artifact-class",
                "command-stdout",
                "--format",
                "json",
            )

        payload = json.loads(output)
        plan = payload["evidenceUploadPlan"]
        self.assertEqual(payload["contractEvents"], [])
        self.assertEqual(plan["uploadDecision"], "allow")
        self.assertEqual(plan["retentionDays"], 30)
        self.assertTrue(plan["deleteLocalAfterUpload"])
        self.assertEqual(plan["evidenceRef"], "evidence:acme:TICKET-0001:host-0001:upload:command-stdout")
        self.assertEqual(plan["billingStatementAttachment"]["billingAccountId"], "org:acme")
        self.assertEqual(plan["billingStatementAttachment"]["runtimeWalletId"], "org:acme:runtime")
        self.assertEqual(plan["billingStatementAttachment"]["statementGroupRef"], "statement-group:support:acme:TICKET-0001")
        self.assertEqual(plan["billingStatementAttachment"]["lineItemType"], "support_evidence_retention_item")

    def test_evidence_plan_upload_refuses_unapproved_sensitive_artifact(self):
        with tempfile.NamedTemporaryFile() as artifact:
            artifact.write(b"dump bytes\n")
            artifact.flush()

            code, stdout, _ = self.run_cli_with_code(
                "evidence",
                "plan-upload",
                "--tenant",
                "acme",
                "--ticket",
                "TICKET-0001",
                "--host",
                "host-0001",
                "--path",
                artifact.name,
                "--artifact-class",
                "minidump",
                "--format",
                "json",
            )

        self.assertEqual(code, 2)
        payload = json.loads(stdout)
        plan = payload["evidenceUploadPlan"]
        self.assertEqual(payload["contractEvents"], [])
        self.assertEqual(plan["uploadDecision"], "refuse")
        self.assertIn("missing required refs", plan["reasons"][0])
        self.assertIsNone(plan["retentionDays"])

    def test_evidence_plan_upload_refuses_unredacted_command_output(self):
        with tempfile.NamedTemporaryFile() as artifact:
            artifact.write(b"TAILSCALE_AUTH_KEY=tskey-secret\n")
            artifact.flush()

            code, stdout, _ = self.run_cli_with_code(
                "evidence",
                "plan-upload",
                "--tenant",
                "acme",
                "--ticket",
                "TICKET-0001",
                "--host",
                "host-0001",
                "--path",
                artifact.name,
                "--artifact-class",
                "command-stdout",
                "--format",
                "json",
            )

        self.assertEqual(code, 2)
        plan = json.loads(stdout)["evidenceUploadPlan"]
        self.assertEqual(plan["uploadDecision"], "refuse")
        self.assertEqual(plan["redactionFindings"], 1)
        self.assertIn("artifact appears to contain unredacted secrets", plan["reasons"])

    def test_evidence_plan_upload_never_allows_secret_artifacts(self):
        with tempfile.NamedTemporaryFile() as artifact:
            artifact.write(b"TAILSCALE_AUTH_KEY=tskey-secret\n")
            artifact.flush()

            code, stdout, _ = self.run_cli_with_code(
                "evidence",
                "plan-upload",
                "--tenant",
                "acme",
                "--ticket",
                "TICKET-0001",
                "--host",
                "host-0001",
                "--path",
                artifact.name,
                "--artifact-class",
                "secret",
                "--approval-ref",
                "approval:acme:TICKET-0001:sensitive",
                "--consent-ref",
                "consent:acme:TICKET-0001:sensitive",
                "--sensitive-exception-ref",
                "exception:acme:TICKET-0001:secret",
                "--format",
                "json",
            )

        self.assertEqual(code, 2)
        plan = json.loads(stdout)["evidenceUploadPlan"]
        self.assertEqual(plan["uploadDecision"], "refuse")
        self.assertIn("artifact class is never uploadable", plan["reasons"])


if __name__ == "__main__":
    unittest.main()
