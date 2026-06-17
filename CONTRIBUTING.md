# Contributing to Zenux Support

Thanks for your interest in contributing. This repository owns the Zenux
IT/support/helpdesk product domain (the `supportctl` operator CLI plus
support-domain contracts and runbooks). We welcome bug reports, fixes, and
documentation improvements.

## Ground rules

- Be respectful. All participation is governed by our
  [Code of Conduct](CODE_OF_CONDUCT.md).
- This project is licensed under **AGPL-3.0-or-later**. By contributing you
  agree your contributions are licensed under the same terms. See
  [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
- **Never commit secrets, credentials, real customer data, or PII.** The
  support domain handles customer identity and consent flows; tests and
  fixtures must use synthetic data only.

## Getting started

1. Fork the repository and create a feature branch off `main`
   (`git checkout -b feat/short-description`).
2. Make focused changes with clear commit messages.
3. Add or update tests where behavior changes.
4. Run the project's lint and test steps before opening a PR.
5. Open a pull request describing the change and the motivation.

## Pull requests

- Keep PRs scoped to a single concern; small PRs review faster.
- Reference any related issue.
- Ensure CI is green. Maintainers review on a best-effort basis.

## Reporting security issues

Do **not** open a public issue for security vulnerabilities. Follow the process
in [SECURITY.md](SECURITY.md).
