# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities privately. **Do not open a public
GitHub issue for security reports.**

- Preferred: use GitHub's **private vulnerability reporting** for this
  repository (the "Report a vulnerability" button under the Security tab).
- We aim to acknowledge reports within a few business days and will keep you
  informed of progress toward a fix.

When reporting, please include:

- A description of the issue and its potential impact.
- Steps to reproduce or a proof of concept.
- Affected versions or components, if known.

## Scope

This policy covers the code in this repository (the `supportctl` CLI and
support-domain contracts). The hosted Zenux control plane and any customer data
it processes are operated separately; vulnerabilities touching hosted
infrastructure or customer data should be reported through the same private
channel and will be routed appropriately.

## Sensitive data

This domain handles customer identity, consent, and support-session data. Never
include real customer data, credentials, or PII in vulnerability reports;
describe the issue with synthetic or redacted examples.
