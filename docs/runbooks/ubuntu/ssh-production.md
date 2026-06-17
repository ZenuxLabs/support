# Ubuntu SSH Production Runbook

Status: planned.

Production Ubuntu support should use OpenSSH Server over Tailscale or another
private transport. It should not expose SSH to the public internet.

Target model:

```text
support laptop
  -> private transport
  -> Ubuntu OpenSSH Server
  -> temporary key-only support user
  -> approved diagnostics and remediation
```

Required before implementation:

- customer-visible bootstrap
- one-off Tailscale enrollment
- `openssh-server` installation and hardening
- key-only SSH configuration
- firewall/private-transport restriction
- diagnostics bundle collector
- offboarding script
- AI command policy
