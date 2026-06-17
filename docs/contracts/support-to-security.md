# Support to Zenux Security Contract

This contract keeps security governance in `ZenuxLabs/Zenux` while allowing the
support product to create customer-visible support records and evidence.

Support does not own approvals, policy, retention, findings, or compliance.
Support calls the Zenux security control plane and records returned ids.

## Approval Request: `support.session.approval_requested`

Required fields:

- `requestId`: stable idempotency key.
- `ticketId`
- `customerId`
- `authorizedContactId`
- `operatorId`
- `deviceRef`
- `purpose`: support reason and planned action category.
- `riskLevel`: `low`, `medium`, `high`, or `break-glass`.
- `requestedCapabilities`: remote desktop, file transfer, diagnostics,
  shell, admin elevation, network change, or reboot.
- `customerConsentRequired`: boolean.
- `evidencePlan`: planned artifacts and redaction state.

Security responds with:

- `approvalRef`
- `decision`: `approved`, `denied`, `needs-human-review`, or `expired`.
- `constraints`: policy constraints support and networking must enforce.
- `expiresAt`

## Consent Event: `support.customer.consent_recorded`

Required fields:

- `ticketId`
- `customerId`
- `authorizedContactId`
- `operatorId`
- `approvalRef`
- `scopeTextRef`: immutable copy of what the customer approved.
- `sessionStartAllowed`: boolean.
- `recordedAt`

Support must record consent before asking networking to create production
customer access, except for explicitly approved emergency break-glass flows.

## Evidence Event: `support.evidence.submitted`

Required fields:

- `ticketId`
- `customerId`
- `operatorId`
- `approvalRef`
- `evidenceBundleId`
- `artifactRefs`: references to redacted logs, command outputs, screenshots, or
  customer summaries.
- `redactionState`: `none-required`, `redacted`, or `requires-review`.
- `retentionClass`: security-owned retention class.

Forbidden fields:

- API tokens
- SSH private keys
- raw customer secrets
- unredacted credentials
- raw diagnostic bundles not approved for upload

## Command Events

Read-only diagnostics and remediation commands are reported as support-owned
events. Zenux security owns the approval and retention decisions; support owns
the command UX and local evidence bundle assembly.

Approval request event: `support.command.approval_requested`

Required fields:

- `eventId`
- `ticketId`
- `customerId`
- `accessSessionId`
- `operatorId`
- `executionAdapter`
- `commandRef`
- `approvalRef`
- `policyDecisionRef`
- `redactionProfile`
- `evidenceRefs`

Execution event: `support.command.executed`

Required fields:

- `eventId`
- `ticketId`
- `customerId`
- `accessSessionId`
- `operatorId`
- `executionAdapter`
- `commandRef`
- `approvalRef`
- `startedAt`
- `finishedAt`
- `exitCode`
- `stdoutRef`
- `stderrRef`
- `redactionProfile`
- `redactionSummary`
- `evidenceRefs`

Raw stdout and stderr are artifacts governed by the evidence policy, not audit
event fields. They must be redacted before upload and may remain local-only
when the ticket policy does not permit retention.

## Closure Gate: `support.ticket.close_requested`

Support can request closure only after:

- customer session end is recorded
- networking access revocation is verified
- command outputs are redacted or marked local-only
- customer summary is prepared when required
- evidence bundle is accepted by Zenux security

Security responds with:

- `closureDecision`: `approved`, `denied`, or `needs-review`
- `missingRequirements`: list of unresolved controls
- `auditRef`
