# Windows Support Demo Runbook

This runbook demonstrates the intended Windows support paths:

- existing private access: validate RDP or SSH over Tailscale
- new customer: bootstrap Tailscale and Windows OpenSSH from a visible customer
  session
- offboarding: remove temporary access and record evidence

It does not use Tailscale SSH for Windows. Windows SSH means regular Windows
OpenSSH Server over private transport.

For cross-platform direction, see `docs/architecture/os-adapters.md`.

## Dogfood Test Node

An existing dogfood Windows node is useful for connectivity tests when online,
but it is not a clean customer onboarding proof if it already has machine
identity, device policy, or private-network state.

Use a fresh Windows VM or clean snapshot for a full new-customer proof.

## Demo A: Existing Node Connectivity

Goal: prove that an existing Windows machine can be reached privately.

Prerequisites:

- a dogfood Windows node is online in the private transport.
- A ticket ID exists for the test.
- The support engineer has approved credentials for the selected access method.
- The tailnet policy permits the required port.

Support laptop checks:

```bash
tailscale status
tailscale ping <windows-hostname>
```

For RDP:

```bash
nc -vz <windows-private-ip> 3389
open "rdp://full%20address=s:<windows-private-ip>"
```

For Windows OpenSSH:

```bash
nc -vz <windows-private-ip> 22
ssh -i ~/.ssh/zenux_support_ed25519 zenux-support@<windows-private-ip>
```

Record in the ticket:

- approver
- session start and stop time
- access method
- scripts run
- output retained or discarded
- offboarding result

## Demo B: New Customer SSH Bootstrap

Goal: prove support when the customer has no existing Tailscale access.

Use a clean Windows VM or a customer-visible elevated PowerShell session. The
customer runs one bootstrap that enrolls Tailscale and configures Windows
OpenSSH Server.

```powershell
$env:TAILSCALE_AUTH_KEY = "tskey-..."
$env:ZENUX_SUPPORT_TICKET_ID = "TICKET-0001"
$env:ZENUX_SUPPORT_HOSTNAME = "host-0001"
$env:ZENUX_SUPPORT_SSH_AUTHORIZED_KEY = "ssh-ed25519 AAAA... zenux-support"
$runner = Join-Path $env:TEMP "zenux-run-verified.ps1"
Invoke-WebRequest -Uri "https://support.example.com/run-verified.ps1" -OutFile $runner
powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Script "customer-ssh-bootstrap.ps1"
Remove-Item $runner -Force
```

From the support laptop:

```bash
tailscale status
tailscale ping host-0001
ssh -i ~/.ssh/zenux_support_ed25519 zenux-support@host-0001
```

The bootstrap target script is hash-verified through `/manifest.json`. The
runner itself still needs signed or pinned delivery before production.

## Demo C: Diagnostics And Offboarding

After SSH or RDP access works, collect diagnostics:

```powershell
$runner = Join-Path $env:TEMP "zenux-run-verified.ps1"
Invoke-WebRequest -Uri "https://support.example.com/run-verified.ps1" -OutFile $runner
powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Script "crash-check.ps1"
Remove-Item $runner -Force
```

Then offboard temporary SSH access from an elevated PowerShell session:

```powershell
$runner = Join-Path $env:TEMP "zenux-run-verified.ps1"
Invoke-WebRequest -Uri "https://support.example.com/run-verified.ps1" -OutFile $runner
powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Script "windows-ssh-offboard.ps1"
Remove-Item $runner -Force
```

If this was a clean customer bootstrap, also remove the Tailscale machine from
the admin console or API and revoke unused keys.

Record:

- diagnostic output retention decision
- Tailscale machine/key cleanup
- temporary user cleanup
- exceptions or incidents

## Pass Criteria

The demo passes only if:

- endpoint access is ticket-scoped
- support access works without public RDP or public SSH exposure
- diagnostics can be collected
- customer-visible consent is recorded
- no Tailscale SSH-to-Windows assumption is used
- temporary access is removed
- final ticket evidence includes start, stop, actions, and offboarding

## Fail Conditions

The demo fails if:

- RDP or SSH is exposed to the public internet
- a reusable long-lived customer auth key is treated as production
- a persistent local admin support account remains after the test
- access is not tied to a ticket
- offboarding evidence is missing
- customer diagnostic data is retained without an approved retention decision
