# Windows Adapter Scripts

Customer-runnable PowerShell scripts for the ZenuxLabs support fabric. These are
served (hash-verified) by the Cloudflare Worker in [`../../worker`](../../worker)
and are part of this open engine. The company's hosted instance configuration
lives separately in the private `ZenuxLabs/support-cloud`.

## Scripts

- `onboarding/join.ps1` — one-command fleet onboarding entry point. Run elevated:
  `irm <base>/join.ps1 | iex`. Installs Tailscale + key-only Windows OpenSSH via
  the verified runner. The authorized SSH key is taken from
  `ZENUX_SUPPORT_SSH_AUTHORIZED_KEY`, then a build-time baked value, then a prompt
  — **a self-hosted build leaves it unset so you authorize your own key, never
  someone else's** (see "Instance key" below).
- `onboarding/customer-ssh-bootstrap.ps1` — enrolls Tailscale and configures
  Windows OpenSSH for a new endpoint.
- `onboarding/windows-ssh-onboard.ps1` — configures Windows OpenSSH when private
  transport already exists.
- `runner/run-verified.ps1` — downloads, SHA256-verifies (against
  `/manifest.json`), and runs a named support script.
- `offboarding/windows-ssh-offboard.ps1` — removes temporary Windows SSH access.
- `diagnostics/crash-check.ps1` — first-pass crash and hardware diagnostic.

## Instance key

`join.ps1` contains `{{SUPPORT_AUTHORIZED_KEY}}`, filled at build time by
`worker/build.py` from the `SUPPORT_AUTHORIZED_KEY` env var:

- **Self-hosting (OSS default):** unset → the placeholder resolves empty →
  `join.ps1` prompts for the SSH key to authorize. You stay in control of which
  key is trusted on your machines.
- **Operating an instance:** set `SUPPORT_AUTHORIZED_KEY` to your own support
  pubkey so the served `join.ps1` bakes it in and onboarding only prompts for the
  tagged Tailscale auth key. (Our deploy does this from `support-cloud`.)

A public SSH key is not a secret; this is instance configuration, not a credential.

See `docs/runbooks/windows/openssh-production.md` for the delivery and deploy model.
