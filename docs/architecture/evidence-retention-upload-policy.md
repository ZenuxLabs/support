# Evidence Retention And Upload Policy

Status: baseline engineering policy for dogfood and prototype use. Paid
customer production still requires legal approval, customer-facing terms, and a
Zenux evidence storage implementation.

This policy applies to support transcripts, command output, diagnostics,
recordings, screenshots, dumps, and customer-provided files handled by the
support fabric.

## Principles

- Collect the minimum evidence needed to resolve the ticket and prove
  offboarding.
- Do not upload evidence without a ticket, tenant, artifact class, retention
  decision, and evidence ref.
- Do not upload secrets, private keys, deploy tokens, Tailscale auth keys, or
  customer credentials.
- Prefer redacted summaries over raw logs, raw command output, dumps,
  screenshots, recordings, or customer files.
- Keep local artifacts temporary and delete them after successful upload or
  retention expiry.
- Treat customer-specific contract, regulatory, or legal-hold requirements as
  overrides that require explicit security/legal approval.

## Artifact Classes

| Artifact class | Default retention | Upload rule |
| --- | ---: | --- |
| `contract-event` | 365 days | Allowed by default. |
| `command-stdout` | 30 days | Allowed after redaction. |
| `command-stderr` | 30 days | Allowed after redaction. |
| `diagnostic-summary` | 90 days | Allowed by default. |
| `diagnostic-bundle` | 30 days | Requires approval and customer consent. |
| `minidump` | 7 days | Requires approval, customer consent, and sensitive exception. |
| `screenshot` | 7 days | Requires approval, customer consent, and sensitive exception. |
| `customer-file` | 7 days | Requires approval, customer consent, and sensitive exception. |
| `session-recording` | 30 days | Requires approval, customer consent, and sensitive exception. |
| `secret` | 0 days | Never upload. |
| `private-key` | 0 days | Never upload. |

Retention is a maximum unless a stricter customer agreement, legal hold, or
incident-response requirement applies.

## Local Evidence

`supportctl --evidence-dir` writes local evidence for dogfood and API-free
operation. Operator machines must treat that directory as sensitive support
data.

Local rules:

- keep artifacts under a ticket-scoped directory
- do not store evidence in consumer sync folders
- delete local artifacts after successful upload or retention expiry
- do not attach local evidence to chat or email unless the ticket policy allows
  that transfer
- if redaction looks insufficient, do not upload the artifact

## Upload Planning

The current CLI has a policy-only planning command. It does not upload data:

```bash
./bin/supportctl evidence plan-upload \
  --tenant acme \
  --ticket TICKET-0001 \
  --host host-0001 \
  --path .support-evidence/stdout.txt \
  --artifact-class command-stdout \
  --format json
```

Sensitive artifact example:

```bash
./bin/supportctl evidence plan-upload \
  --tenant acme \
  --ticket TICKET-0001 \
  --host host-0001 \
  --path .support-evidence/minidump.dmp \
  --artifact-class minidump \
  --approval-ref approval:acme:TICKET-0001:minidump \
  --consent-ref consent:acme:TICKET-0001:minidump \
  --sensitive-exception-ref exception:acme:TICKET-0001:minidump \
  --format json
```

The future upload command must use the same policy decision before writing to
Zenux evidence storage.

Because `evidence plan-upload` is policy-only, it must not emit a billable
usage event by itself. The command only returns the statement-group attachment
metadata that a later real upload step would need.

`evidence plan-upload` also scans the local artifact for obvious unredacted
secret patterns. If it detects a Tailscale auth key, private key block, or
secret-like environment assignment, the decision is `refuse` even for otherwise
allowed classes such as `command-stdout`.

## Customer Consent

Customer-visible support language must clearly state which evidence classes may
be collected:

- command output and system logs for diagnostics
- diagnostic summaries and support bundle contents
- optional screenshots, recordings, dumps, or customer files only when
  explicitly approved
- retention period and deletion path
- who can access the retained evidence

Do not rely on a generic remote-support consent prompt for dumps, recordings,
screenshots, or customer files.

## Redaction

The default redaction profile is `support-diagnostics-default`.

It must remove or block:

- deploy tokens and API keys
- Tailscale auth keys
- SSH private keys
- customer credentials
- obvious secret environment assignments

If an artifact still appears to contain sensitive content after redaction, the
upload decision must be refused or escalated to a sensitive exception.

## Zenux Evidence Sink

The future Zenux evidence API must preserve:

- `tenantId`
- `ticketId`
- `deviceRef`
- artifact class
- evidence ref
- approval ref
- consent ref
- sensitive exception ref when required
- retention expiry
- redaction profile
- uploader identity
- upload timestamp
- content hash

The API should store metadata separately from artifact bodies so audit records
can remain even when artifact bodies expire.

## References

Guidance reviewed on 2026-05-18:

- NIST SP 800-92, Guide to Computer Security Log Management:
  https://csrc.nist.gov/pubs/sp/800/92/final
- NIST Cybersecurity Framework 2.0:
  https://www.nist.gov/cyberframework
- FTC Protecting Personal Information, A Guide for Business:
  https://www.ftc.gov/business-guidance/resources/protecting-personal-information-guide-business
