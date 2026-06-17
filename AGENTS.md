# support

Zenux IT/support/helpdesk domain.

This repo owns customer-facing support workflow: tickets, customer-visible
sessions, consent, diagnostics/remediation flow, customer summaries, evidence
bundle creation, and offboarding closure gates.

Do not add reusable networking fabric implementation here. Networking primitives
belong in `ZenuxLabs/networking`.

Do not duplicate Zenux security control-plane behavior here. Approvals, audit,
findings, policy, compliance, and evidence retention belong in `ZenuxLabs/Zenux`
or should be consumed through its contract.

Use a managed secret store as the canonical secret store. Never commit deploy
tokens, Tailscale keys, SSH private keys, customer diagnostic output, or
tenant-specific configuration.

The live script-delivery plane (Worker, signed customer-runnable scripts,
provider key/tunnel plumbing) is operated separately and is not part of this
open repo.
