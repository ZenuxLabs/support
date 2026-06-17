# Zenux Support

Zenux IT/support/helpdesk product domain.

This repo owns the customer support workflow. It should integrate with the
Zenux networking domain for private access and with the Zenux security control
plane for approvals, audit, findings, evidence, and compliance.

## Domain Ownership

Owns:

- ticket workflow
- customer-visible support sessions
- customer identity and authorized-contact checks
- consent and scope approval
- diagnostics and remediation workflow
- customer summaries
- support evidence bundle creation
- offboarding closure gates

Does not own:

- reusable networking, mesh access, DNS, tunnels, VPN, or ZTNA lifecycle
- security posture, approvals engine, audit retention, findings, or compliance
- tenant-specific secrets or customer-specific configuration

## Staging Implementation

The live delivery plane (the script-serving Worker, signed customer-runnable
scripts, and provider key/tunnel plumbing) is operated separately from this
repo. This repo owns the support-domain charter, contracts, the `supportctl`
operator CLI, and the runbooks. The delivery plane is intentionally not part of
this open repo.

## Operator CLI

The first support-owned operator interface is `supportctl`:

```bash
./bin/supportctl --help
./bin/supportctl bootstrap windows --tenant acme --ticket TICKET-0001 --hostname host-0001
./bin/supportctl diag windows --tenant acme --ticket TICKET-0001 --host host-0001 --format json
./bin/supportctl evidence plan-upload --tenant acme --ticket TICKET-0001 --host host-0001 --path .support-evidence/stdout.txt --artifact-class command-stdout
```

`supportctl` plans and records support workflow actions. It does not own
Tailscale/provider key creation, reusable private transport, or Zenux security
approval storage. Those stay behind the networking and security contracts.

## Runbooks

- [Support CLI architecture](docs/architecture/cli.md)
- [Production customer support architecture](docs/architecture/production-customer-support.md)
- [OS adapter architecture](docs/architecture/os-adapters.md)
- [Evidence retention and upload policy](docs/architecture/evidence-retention-upload-policy.md)
- [Windows OpenSSH production runbook](docs/runbooks/windows/openssh-production.md)
- [Windows support demo runbook](docs/runbooks/windows/support-demo.md)
- [macOS SSH production runbook](docs/runbooks/macos/ssh-production.md)
- [Ubuntu SSH production runbook](docs/runbooks/ubuntu/ssh-production.md)

## Test

```bash
python3 -m py_compile supportctl/*.py tests/*.py
python3 -m unittest discover -s tests -v
```

CI runs the lightweight support CLI checks on GitHub-hosted capacity. The
support CLI check is pure Python/static validation, so it does not require a
self-hosted runner.

## Initial Contract Shape

Support -> Networking:

- request private access for a ticket/customer/device
- receive provider session metadata or connection instructions
- request offboarding and revocation verification

Support -> Security:

- request session approval
- record customer consent
- record command approvals and outputs
- submit evidence bundle and customer summary

## Billing Control Plane

Support does not own a separate billing model. Customer-visible support work
must map into the shared ecosystem billing plane:

- canonical `billing_account` scope derives from the support customer/tenant
- canonical `runtime_wallet` scope derives from that billing account
- runtime-heavy diagnostics and offboarding runs consume runtime wallet budget
- access/bootstrap planning and evidence retention remain entitlement-scoped
- planning commands carry statement/chargeback attachment metadata only
- executed runtime work must emit an explicit billing outcome event before it can settle into the central ledger

## Contracts

- [Support to networking access contract](docs/contracts/support-to-networking.md)
- [Support to Zenux security contract](docs/contracts/support-to-security.md)

## Current Status

This repo now owns the support-domain charter, first contract drafts, the
`supportctl` operator CLI, and support runbooks.

A separate, non-public staging implementation still serves the live
script-delivery Worker and customer-runnable scripts until a signed script
release/deploy path is ready here. The first internal dogfood tenant is treated
as a tenant, not the product owner.
