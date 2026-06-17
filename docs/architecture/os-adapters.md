# OS Adapter Architecture

The helpdesk control plane must support Windows, macOS, and Ubuntu without
forking the customer support workflow.

These adapters belong to the ZenuxLabs support fabric. An internal dogfood
tenant can use them while the fabric is validated.

The shared model is:

```text
ticket
  -> consent
  -> OS detection
  -> private transport enrollment
  -> OS-specific execution adapter
  -> diagnostics/remediation
  -> evidence
  -> offboarding
```

## Shared Contract

Each OS adapter must provide:

- bootstrap instructions for a new customer
- private transport enrollment
- SSH or shell execution setup
- diagnostics bundle collection
- remediation command policy
- offboarding
- evidence fields

## Windows Adapter

Status: initial implementation.

Execution channel:

- Windows OpenSSH Server over Tailscale or another private transport

Implemented scripts:

- `scripts/windows/onboarding/customer-ssh-bootstrap.ps1`
- `scripts/windows/onboarding/windows-ssh-onboard.ps1`
- `scripts/windows/offboarding/windows-ssh-offboard.ps1`
- `scripts/windows/diagnostics/crash-check.ps1`

Primary runbook:

- `docs/runbooks/windows/openssh-production.md`

## macOS Adapter

Status: planned.

Likely execution channel:

- built-in macOS Remote Login (`sshd`) over Tailscale or another private
  transport

Planned scripts:

- `scripts/macos/onboarding/customer-ssh-bootstrap.sh`
- `scripts/macos/diagnostics/collect-support-bundle.sh`

Production notes:

- require customer-visible consent
- prefer a temporary support user or customer-approved existing admin
- avoid persistent unattended access by default
- use `systemsetup -setremotelogin on` only with approval
- offboard by removing temporary users, authorized keys, and Tailscale device

## Ubuntu Adapter

Status: planned.

Likely execution channel:

- OpenSSH Server over Tailscale or another private transport

Planned scripts:

- `scripts/ubuntu/onboarding/customer-ssh-bootstrap.sh`
- `scripts/ubuntu/diagnostics/collect-support-bundle.sh`

Production notes:

- install `openssh-server` only with consent
- use key-only authentication
- restrict SSH to private transport through firewall or security group policy
- create temporary least-privilege user by default
- use `sudo` only after explicit approval
- offboard by removing temporary users, authorized keys, and Tailscale device

## AI Runner

The AI runner should call an OS adapter instead of directly calling arbitrary
shell commands. The adapter owns:

- command allowlist
- shell quoting rules
- diagnostic collection path
- sensitive-output handling
- remediation approval requirements
- offboarding checks
