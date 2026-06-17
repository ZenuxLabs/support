# Windows Adapter Scripts

Status: live in staging, pending signed release extraction.

These scripts are part of the ZenuxLabs support fabric.

The customer-runnable PowerShell scripts themselves are served from a separate,
non-public delivery plane (a hash-verifying Worker and signed scripts) until a
signed release path is implemented in this repo. This folder documents the
script contract and runbook references; the script bodies are intentionally not
part of this open repo.

Current staging scripts:

- `onboarding/customer-ssh-bootstrap.ps1` - enrolls Tailscale and configures
  Windows OpenSSH for a new customer endpoint
- `onboarding/windows-ssh-onboard.ps1` - configures Windows OpenSSH when private
  transport already exists
- `offboarding/windows-ssh-offboard.ps1` - removes temporary Windows SSH access
- `diagnostics/crash-check.ps1` - first-pass crash and hardware diagnostic

See `docs/runbooks/windows/openssh-production.md`.
