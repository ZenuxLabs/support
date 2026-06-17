# ZenuxLabs Support Fabric Architecture

This document defines the target production support model for AI-assisted
customer IT helpdesk across Windows, macOS, and Ubuntu.

## Decision

Production customer support must be UI-first and AI-assisted.

ZenuxLabs should own the customer support control plane as part of the networking
and security fabric. The first internal dogfood tenant should be treated as a
tenant, not the owner of the fabric.

Use a dedicated remote support engine behind our control plane. Prefer an owned
or self-hostable engine such as RustDesk Server Pro for the default path, while
keeping adapter support for customer-required tools such as TeamViewer,
AnyDesk, BeyondTrust, Microsoft Remote Help, FortiClient, Palo Alto
GlobalProtect/Prisma Access, or Tailscale.

Use Tailscale plus OS-native remote access only as an approved technical
escalation path. Use SSH as the preferred closed-loop execution channel for
AI-assisted diagnostics and remediation after customer consent.

Do not present RDP, SSH, or script execution as the primary customer support
product. The product is the helpdesk workflow, AI triage, controlled execution,
evidence, and offboarding.

Zenux is already the security command center/control plane for assets, findings,
cases, approvals, playbooks, evidence, audit, integrations, and compliance
reporting. This support fabric should integrate with Zenux for governance and
evidence. It should not assume the top-level `zenux` CLI belongs to remote
support unless a product-wide CLI strategy is approved.

## Why

Production support has legal, security, and customer-trust requirements that
plain RDP does not satisfy by itself:

- customer-visible consent
- identity-backed support engineer access
- role-based permissions
- session start and stop logging
- file-transfer and clipboard controls
- elevation controls
- session recording or audit trails where legally approved
- customer ability to stop the session
- offboarding evidence

RDP is useful for Windows administration, but it is not enough as the main
customer helpdesk experience. The customer-facing product should be our support
workflow, evidence model, consent flow, diagnostics, and offboarding controls.
The remote desktop engine should be replaceable.

## Recommended Stack

### Owned Control Plane

Build and operate our own support control plane for:

- customer support portal
- ticket creation and authorization
- customer identity and authorized-contact verification
- per-session consent
- remote support provider selection
- support session launch links or codes
- diagnostics bundle collection
- evidence retention
- offboarding checklist and closure gate
- customer safety and anti-scam verification copy
- provider-neutral audit timeline
- AI diagnostic and remediation workflow
- command approval policy
- Zenux evidence, approval, audit, and playbook sync

The control plane must not depend on one vendor-specific session model. It
should store provider-agnostic evidence fields and provider-specific metadata
separately.

It also must not invent a support-local billing path. Runtime-heavy support
automation should use the shared `billing_account` and `runtime_wallet` model
from the central billing control plane, and evidence-retention items should be
attachable to monthly statements or internal chargeback exports.

### Default Remote Support Engine

Choose one production remote support platform with:

- SSO and MFA for engineers
- named engineer accounts
- RBAC or granular support roles
- customer-visible consent prompts
- session links or one-time session codes
- session logging
- session recording controls
- file-transfer controls
- elevation controls
- exportable audit reports or API access

Default candidate:

- RustDesk Server Pro, because it is self-hostable and gives us a path toward
  owned infrastructure, custom clients, OIDC/LDAP/2FA, device management, access
  control, control roles, and log management.

Supported provider adapters:

- Microsoft Remote Help, if support is primarily for devices/users managed
  through Microsoft Entra ID and Intune.
- TeamViewer Tensor, if we need a broadly deployable commercial support tool
  with SSO and conditional access.
- BeyondTrust Remote Support, if we need stronger privileged-access and audit
  posture for regulated or enterprise customers.
- AnyDesk enterprise configuration only if SSO/MFA, access control, recording,
  and unattended-access restrictions are centrally enforced.
- FortiClient/FortiGate/FortiSASE or Palo Alto GlobalProtect/Prisma Access,
  when the customer requires their existing ZTNA/VPN stack for access routing.

Avoid consumer-grade unattended AnyDesk, TeamViewer, or RustDesk OSS/public
server setups for production customer support.

Do not build a custom remote-control protocol unless there is a separate
security-product roadmap, patching budget, and external audit plan. Owning the
control plane gives us portability without taking on unnecessary protocol and
agent risk.

### Private Transport Layer

Use Tailscale only as private transport for approved escalations.

Allowed over Tailscale:

- RDP to a Windows endpoint on TCP 3389
- WinRM or PowerShell Remoting for scripted diagnostics
- OpenSSH Server on Windows, macOS, or Ubuntu when explicitly installed or
  enabled and approved
- file transfer through an approved support tool or ticket workflow

### AI Execution Layer

The AI helpdesk loop should use SSH for controlled execution when a ticket needs
repeatable diagnostics or remediation.

The runner should:

- load the ticket context and approved scope
- connect using a ticket-scoped support identity
- run only approved diagnostic commands by default
- require approval for remediation commands
- capture command, exit code, stdout, stderr, and timestamps
- redact or restrict sensitive output before retention
- produce a human-readable ticket summary
- verify offboarding before closure

The runner must not:

- run arbitrary shell commands without policy approval
- collect dumps or sensitive files without explicit consent
- persist access after ticket closure
- bypass customer-visible support when invasive work is needed

Not allowed:

- public internet RDP
- Tailscale SSH as the assumed Windows destination model
- long-lived shared support accounts
- broad `autogroup:admin` access to customer devices
- persistent unattended access without a signed managed-support agreement

### Diagnostics Layer

The support scripts in this repo should become a signed support bundle
collector.

The production collector should gather:

For all supported operating systems:

- OS version, hardware model, disk, memory, and network summary
- recent critical system logs
- update status
- security and disk-health indicators where available

For Windows:

- Windows System and Application event logs
- Kernel-Power, BugCheck, WHEA, disk, storage, and thermal-related events
- Reliability Monitor records
- power configuration
- hardware and driver inventory
- optional minidumps when explicitly approved
- optional live sensor logs when temperature issues must be reproduced

For macOS and Ubuntu:

- system logs relevant to crashes, panics, restarts, kernel, disk, network, and
  package/update state
- optional crash reports, panic logs, and hardware diagnostics where available

Default behavior should be local zip output and no upload. Upload should require
a ticket-scoped destination and customer consent.

Evidence retention and upload decisions must follow
[evidence-retention-upload-policy.md](evidence-retention-upload-policy.md).

## Production Session Flow

1. Customer opens a ticket through a known tenant channel.
2. Support verifies the authorized customer contact.
3. The support control plane chooses the remote support provider for the ticket.
4. Customer sees and accepts the support session.
5. Engineer performs normal UI support through the support platform.
6. If deeper access is required, engineer requests escalation approval.
7. Tailscale access is enrolled only for the ticket.
8. OS-native remote access or SSH is used only for the approved task.
9. AI collects diagnostics and proposes remediation within policy.
10. Engineer or policy approval gates remediation commands.
11. Diagnostics are collected with the minimum required data.
12. Temporary accounts, Tailscale devices, keys, and permissions are removed.
13. Ticket is closed only after evidence and offboarding are recorded.

## When RDP Is Allowed

RDP over Tailscale is allowed for production only when all of the following are
true:

- customer has approved the escalation
- ticket ID is recorded
- support engineer identity is named
- endpoint is reachable only through private transport
- RDP is not exposed to the public internet
- account used for access is approved and temporary unless customer-managed
- session start and end time are recorded
- offboarding is completed

RDP is not allowed as the default customer support entry point.

## Evidence Required Per Ticket

Every production support ticket should retain:

- ticket ID
- customer organization
- authorized contact
- support engineer identity
- consent timestamp and method
- support platform/session ID
- access method used
- escalation approval if RDP, WinRM, or shell access is used
- start and stop time
- scripts or commands run
- AI-generated recommendations and approvals
- files transferred
- diagnostic output retained
- recordings retained or explicitly not retained
- Tailscale machine/key lifecycle
- temporary user lifecycle
- offboarding completion
- exceptions or incidents

Raw evidence upload is not automatic. Before uploading command output,
diagnostic bundles, recordings, screenshots, dumps, or customer files, the
artifact class must be evaluated against the evidence retention and upload
policy.

## Legal Gate

Production use is blocked until legal approves:

- support authorization terms
- per-session consent language
- privacy notice for diagnostics, recordings, screenshots, logs, and dumps
- data retention and deletion policy
- subprocessor list
- unattended access terms or prohibition
- customer anti-scam verification language

Do not claim SOC 2, ISO 27001, HIPAA, PCI, GDPR, or similar compliance unless
there is a separate legal and audit basis for that claim.

## Security Gate

Production use is blocked until security confirms:

- engineer SSO and MFA
- least-privilege support roles
- remote support platform audit logging
- Tailscale ACLs scoped to support roles and required ports
- one-off or short-lived customer enrollment keys
- no persistent shared customer support admin accounts
- signed or pinned runner delivery
- target script hash verification through the published manifest
- offboarding automation or checklist
- log retention and access controls
- incident response path

## Vendor Selection Recommendation

Default to our own support control plane plus RustDesk Server Pro as the first
self-hosted remote support engine to pilot.

Keep provider adapters for TeamViewer Tensor, BeyondTrust Remote Support,
AnyDesk Enterprise, Microsoft Remote Help, Tailscale, FortiClient, and Palo Alto
GlobalProtect/Prisma Access so we can satisfy customer-specific requirements
without rewriting the support workflow.

If we only support customers in our Microsoft-managed environment, evaluate
Microsoft Remote Help first.

If we need a fast lower-friction pilot, AnyDesk enterprise can be evaluated, but
only with centralized policy, MFA, unattended-access restrictions, and audit
settings. Do not use ad hoc consumer AnyDesk for production customer support.

RustDesk is attractive when self-hosting and data control matter. Treat
RustDesk Server Pro as the production candidate, not the OSS server alone. The
OSS server gives us self-hosted ID and relay infrastructure, but Pro is the path
for web console, API, OIDC, LDAP, 2FA, device management, access control,
control roles, and log management. We should validate session recording,
customer consent UX, log export, support workflows, update process, and abuse
prevention before selecting it.

FortiClient and Palo Alto are not default helpdesk tools. Treat them as
customer-required access-routing adapters for managed enterprise environments,
not as the primary support UI.

## References

Guidance reviewed on 2026-05-17:

- CISA Guide to Securing Remote Access Software:
  https://www.cisa.gov/resources-tools/resources/guide-securing-remote-access-software
- NIST SP 800-46 Rev. 2:
  https://csrc.nist.gov/pubs/sp/800/46/r2/final
- Microsoft Remote Help:
  https://learn.microsoft.com/en-us/intune/intune-service/fundamentals/remote-help
- RustDesk self-host:
  https://rustdesk.com/docs/en/self-host/
- RustDesk Server Pro:
  https://rustdesk.com/docs/en/self-host/rustdesk-server-pro/
- RustDesk Server Pro access control:
  https://rustdesk.com/docs/en/self-host/rustdesk-server-pro/permissions/
- RustDesk Server Pro control roles:
  https://rustdesk.com/docs/en/self-host/rustdesk-server-pro/control-role/
- Tailscale RDP:
  https://tailscale.com/docs/solutions/access-remote-desktops-using-windows-rdp
- Tailscale network flow logs:
  https://tailscale.com/docs/features/logging/network-flow-logs
- Tailscale log streaming:
  https://tailscale.com/docs/features/logging/log-streaming
- BeyondTrust Remote Support audit:
  https://www.beyondtrust.com/products/remote-support/features/audit
- TeamViewer Tensor SSO:
  https://support.teamviewer.com/en/support/solutions/articles/75000128740-single-sign-on-sso-
- TeamViewer Tensor Conditional Access:
  https://community.teamviewer.com/English/kb/articles/108699-conditional-access
- AnyDesk session recording:
  https://support.anydesk.com/docs/session-recording
