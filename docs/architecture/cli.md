# Support Operator CLI Architecture

The support operator CLI should be the engineer and automation interface for the
remote access fabric.

The CLI is not a replacement for the customer-visible helpdesk UI or for the
Zenux security command center. It is a narrow access-orchestration tool for
engineers and AI runners after a ticket has authorization, consent, and scope.

## Relationship To Zenux

Zenux is already a security command center/control plane. Its core product owns
assets, findings, cases, approvals, playbooks, evidence, audit, integrations,
and compliance reporting.

This repo should integrate with Zenux rather than claim the top-level `zenux`
binary by default. The remote support CLI should emit or sync:

- supported customer devices as assets
- support tickets as cases or linked external cases
- access requests as approvals
- diagnostic and remediation steps as playbook runs
- transcripts, logs, hashes, and offboarding proof as evidence
- every lifecycle mutation as audit events

If Zenux later gets a formal product-wide CLI, this tool can become a
`zenux support ...` command group. Until that is approved, the working binary
name is `supportctl`.

## Goals

- make secure remote access repeatable
- hide provider-specific details behind adapters
- support Windows, macOS, and Ubuntu
- generate customer bootstrap instructions
- open short-lived private access
- run approved diagnostics
- execute approved remediation commands
- collect evidence
- enforce offboarding before closure

## Non-Goals

- building a custom remote desktop protocol
- bypassing customer consent
- replacing legal/customer-facing support terms
- exposing public SSH/RDP
- allowing arbitrary AI shell execution

## Command Shape

Working binary name:

```bash
supportctl
```

Core commands:

```bash
supportctl tenant list
supportctl ticket open --tenant acme --ticket TICKET-0001
supportctl device bootstrap --tenant acme --ticket TICKET-0001 --os windows
supportctl device enroll --tenant acme --ticket TICKET-0001 --provider tailscale
supportctl ssh open --tenant acme --ticket TICKET-0001 --device host-0001
supportctl diag collect --tenant acme --ticket TICKET-0001 --device host-0001
supportctl ai plan --tenant acme --ticket TICKET-0001
supportctl ai run --tenant acme --ticket TICKET-0001 --approval APPROVAL-ID
supportctl evidence show --tenant acme --ticket TICKET-0001
supportctl offboard --tenant acme --ticket TICKET-0001 --device host-0001
```

## Adapter Model

The CLI should call adapters instead of hardcoding one provider or OS.

Provider adapters:

- `tailscale`
- `rustdesk`
- `teamviewer`
- `anydesk`
- `beyondtrust`
- `remote-help`
- `forticlient`
- `paloalto`

OS adapters:

- `windows`
- `macos`
- `ubuntu`

Execution adapters:

- `ssh`
- `rdp`
- `winrm`
- `provider-session`

## Data Model

Minimum local/control-plane objects:

- tenant
- ticket
- authorized contact
- device
- enrollment key
- access session
- command approval
- command transcript
- diagnostic bundle
- evidence record
- offboarding record

## AI Boundary

AI can request plans and commands through the CLI, but the CLI owns enforcement.

Allowed without extra approval:

- read-only diagnostics
- inventory
- event/log collection through approved scripts
- health checks

Requires approval:

- changes to system configuration
- package install/uninstall
- account changes
- reboot/shutdown
- file transfer
- dump collection
- persistent access

Every AI-triggered command must produce an evidence record.

## First Milestone

Milestone 1 does not build the full control plane. It provides a useful local
CLI wrapper around the current support workflow:

```bash
./bin/supportctl key create --tenant acme --ticket TICKET-0001 --hostname host-0001
./bin/supportctl bootstrap windows --tenant acme --ticket TICKET-0001 --hostname host-0001 --authorized-key-file ~/.ssh/zenux_support_ed25519.pub
./bin/supportctl ssh windows --host host-0001
./bin/supportctl diag windows --tenant acme --ticket TICKET-0001 --host host-0001
./bin/supportctl offboard windows --tenant acme --ticket TICKET-0001 --host host-0001
```

`key create` does not create a Tailscale key in this repo. It emits or prints a
support-owned access request that must be handled by `ZenuxLabs/networking`.

Planned contract evidence can be written locally before API integration:

```bash
./bin/supportctl diag windows --tenant acme --ticket TICKET-0001 --host host-0001 --evidence-dir .support-evidence --format json
```

Upload policy can be planned without uploading data:

```bash
./bin/supportctl evidence plan-upload --tenant acme --ticket TICKET-0001 --host host-0001 --path .support-evidence/stdout.txt --artifact-class command-stdout --format json
```

This gives us a clean operator interface while the backing implementation still
uses the staging Worker-hosted scripts. Networking-owned key creation, private
transport setup, and revocation stay behind the support-to-networking contract.
Windows script execution goes through `run-verified.ps1`, which downloads
`/manifest.json`, verifies the target script SHA256 hash, and only then runs the
selected script.

The baseline implementation is safe by default:

- command output is printed, not executed
- local SSH-backed actions require `--execute`
- JSON output exposes command, warnings, and Zenux mapping hints for AI runners
- target scripts are hash-verified before execution
- the runner still needs signed or pinned delivery before real production use

## Contract Gate

The CLI can emit local JSON evidence that matches
[support-to-networking.md](../contracts/support-to-networking.md) and
[support-to-security.md](../contracts/support-to-security.md) by passing
`--evidence-dir`.

Until the Zenux APIs exist, these files distinguish support workflow events from
networking access events and security approval/audit records so the later repo
split does not require changing the operator UX. When `diag windows --execute`
is run with `--evidence-dir`, the CLI also writes a `support.command.executed`
event plus a `support.billing.usage_recorded` event that settles the earlier
runtime-wallet planning record with exit code and evidence refs.

`evidence plan-upload` enforces the baseline rules in
[evidence-retention-upload-policy.md](evidence-retention-upload-policy.md). It
does not upload artifacts yet and does not emit a billable usage event; it
exists so the upload policy can be tested before the Zenux evidence API is
wired in.
