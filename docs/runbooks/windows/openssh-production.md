# Production Windows SSH

This is the first implemented OS adapter for the AI helpdesk: SSH to a Windows
machine easily without exposing SSH to the public internet.

Use regular Windows OpenSSH Server over a private transport such as Tailscale.
Do not use Tailscale SSH for Windows destinations.

## Target Model

```text
support engineer laptop
  -> Tailscale/private network
  -> Windows OpenSSH Server on TCP/22
  -> temporary key-only support account
  -> approved diagnostics and remediation
```

Default controls:

- SSH is reachable only over private transport.
- SSH uses public key authentication.
- Password authentication is disabled.
- A temporary local Windows user is created.
- The user expires automatically.
- The Windows firewall allows TCP/22 only from Tailscale address ranges.
- Offboarding removes the temporary user and support firewall rule.

## Support Engineer Setup

Create an SSH key for support access:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/zenux_support_ed25519 -C "zenux-support"
```

Show the public key:

```bash
cat ~/.ssh/zenux_support_ed25519.pub
```

## Windows Endpoint Onboarding

Run from an elevated, customer-visible PowerShell session on the Windows
endpoint.

### New Customer With No Tailscale

For a brand-new customer device, the customer must run one visible bootstrap
from an elevated PowerShell session. This installs Tailscale, joins the device
to the private tailnet with a ticket-scoped auth key, then configures Windows
OpenSSH Server for key-only access.

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

Use a one-off, short-lived Tailscale auth key for the ticket. Do not use
reusable 90-day keys as the production default.

### Existing Private Network Access

If Tailscale or another private path is already present:

```powershell
$env:ZENUX_SUPPORT_TICKET_ID = "TICKET-0001"
$env:ZENUX_SUPPORT_SSH_AUTHORIZED_KEY = "ssh-ed25519 AAAA... zenux-support"
$runner = Join-Path $env:TEMP "zenux-run-verified.ps1"
Invoke-WebRequest -Uri "https://support.example.com/run-verified.ps1" -OutFile $runner
powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Script "windows-ssh-onboard.ps1"
Remove-Item $runner -Force
```

This verifies the target support script hash through `/manifest.json`. The
runner itself still needs signed or pinned delivery before real customer
production.

The script:

- installs OpenSSH Server if needed
- creates or updates `zenux-support`
- installs the provided public key
- disables SSH password authentication
- restricts sshd to `zenux-support`
- restricts Windows Firewall TCP/22 to Tailscale ranges
- restarts `sshd`

## Connect

From the support engineer laptop:

```bash
tailscale ping <windows-hostname-or-ip>
nc -vz <windows-tailscale-ip> 22
ssh -i ~/.ssh/zenux_support_ed25519 zenux-support@<windows-tailscale-ip>
```

## Run Diagnostics

Once connected:

```powershell
hostname
whoami
powershell -NoProfile -ExecutionPolicy Bypass -Command "$runner = Join-Path $env:TEMP 'zenux-run-verified.ps1'; Invoke-WebRequest -Uri 'https://support.example.com/run-verified.ps1' -OutFile $runner; powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Script 'crash-check.ps1'; Remove-Item $runner -Force"
```

The target diagnostic script is hash-verified. The production target is a
signed support bundle collector with signed or pinned runner delivery.

## AI Runner Boundary

The AI runner may use this SSH channel after ticket consent and access approval.

Allowed by default:

- identify host and logged-in support user
- collect event logs through approved scripts
- collect Reliability Monitor records
- inspect disk, driver, power, and update status
- summarize findings

Requires explicit approval:

- changing system settings
- installing or uninstalling software
- collecting dumps
- transferring files
- rebooting
- creating admin-level access

Every command run through SSH should be recorded with timestamp, command, exit
code, and output retention decision.

## Offboard

Run from an elevated PowerShell session on the Windows endpoint:

```powershell
$runner = Join-Path $env:TEMP "zenux-run-verified.ps1"
Invoke-WebRequest -Uri "https://support.example.com/run-verified.ps1" -OutFile $runner
powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Script "windows-ssh-offboard.ps1"
Remove-Item $runner -Force
```

This verifies the target offboarding script hash through `/manifest.json`.

Offboarding removes:

- local `zenux-support` user
- ZenuxLabs Support Fabric SSH firewall rule

If the customer does not want OpenSSH Server left running:

```powershell
$runner = Join-Path $env:TEMP "zenux-run-verified.ps1"
Invoke-WebRequest -Uri "https://support.example.com/run-verified.ps1" -OutFile $runner
powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Script "windows-ssh-offboard.ps1" -ScriptArgs "-DisableSshd"
Remove-Item $runner -Force
```

## Tailnet Policy

The tailnet policy should allow only support engineers to reach customer Windows
SSH on TCP/22.

Example grant:

```jsonc
{
  "groups": {
    "group:support": ["support-engineer@example.com"]
  },
  "tagOwners": {
    "tag:customer": ["group:support"]
  },
  "grants": [
    {
      "src": ["group:support"],
      "dst": ["tag:customer"],
      "ip": ["22"]
    }
  ]
}
```

Do not grant `autogroup:admin` broad access to customer devices for production.

## Admin Access

The default SSH account is intentionally non-admin.

If admin privileges are required, prefer a customer-visible RDP or remote
support session for elevation. Windows OpenSSH admin accounts use
`C:\ProgramData\ssh\administrators_authorized_keys`, which has broader risk
because keys in that file can authorize administrative logons. Treat admin SSH
as a separate escalation requiring explicit approval.

## Production Gate

This path is production-acceptable only after:

- scripts are signed and hash-verified
- Tailscale keys are one-off and short-lived
- ACLs/grants restrict source group and destination port
- support session is tied to a ticket
- customer consent is recorded
- offboarding evidence is recorded
- retained diagnostics are covered by the legal retention policy

## References

Guidance reviewed on 2026-05-17:

- Microsoft OpenSSH key management:
  https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement
- Microsoft OpenSSH Server configuration for Windows:
  https://learn.microsoft.com/windows-server/administration/openssh/openssh-server-configuration
- Microsoft OpenSSH firewall troubleshooting:
  https://learn.microsoft.com/troubleshoot/windows-server/system-management-components/troubleshoot-openssh-windows-firewall-port22
- Tailscale SSH limitations:
  https://tailscale.com/docs/features/tailscale-ssh
- Tailscale ACLs and grants:
  https://tailscale.com/kb/1018/acls/
