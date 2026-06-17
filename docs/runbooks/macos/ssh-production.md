# macOS SSH Production Runbook

Status: planned.

Production macOS support should use built-in macOS Remote Login (`sshd`) over
Tailscale or another private transport. It should not expose SSH to the public
internet.

Target model:

```text
support laptop
  -> private transport
  -> macOS Remote Login
  -> temporary key-only support access
  -> approved diagnostics and remediation
```

Required before implementation:

- customer-visible bootstrap
- temporary support identity design
- key-only SSH configuration
- firewall/private-transport restriction
- diagnostics bundle collector
- offboarding script
- AI command policy
