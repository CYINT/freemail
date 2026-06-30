# Deliverability And Abuse Policy

FreeMail is in a controlled private-beta posture. Do not expose the stack directly to the public internet until the release gates in `docs/milestones.md` are complete.

## Baseline Controls

- Publish the generated MX, SPF, DKIM, and DMARC records for every hosted domain.
- Run `POST /api/v1/admin/domains/{domainId}/dns/verify` with observed DNS records before controlled-domain mail-flow tests.
- Keep DMARC at `p=quarantine` or stricter for beta domains.
- Keep submission authenticated and private to approved users.
- Keep API and web bindings loopback/VPN-only for the current `freemail.kuzuryu.ai` deployment.
- Keep per-mailbox outbound send and recipient caps enabled unless a documented operator decision disables a cap.
- Keep attachment size and content-type controls enabled.

## Abuse Response

- Treat unexpected outbound volume, repeated recipient refusal, queue growth, or external abuse complaints as a beta-blocking incident.
- Preserve audit evidence: mailbox address, timestamps, queue state, rate-limit counters, and relevant SMTP error text.
- Use the admin status endpoints to suspend affected domains, users, mailboxes, aliases, or DKIM keys while preserving audit history.
- Suspend or rotate the affected mailbox credentials in the mail core before raising global limits.
- Do not add proprietary blocklists, reputation feeds, or spam engines unless their licenses are compatible with AGPL distribution or they are optional external integrations.

## Release Gates

- DNS posture verification must be green for each beta domain.
- `scripts/private_beta_gate.py` must pass for the runtime boundary, DNS posture, mail-flow evidence, queue evidence, backup evidence, restore-drill evidence, and decision-owner acceptance for every controlled beta domain.
- Local DKIM-signing smoke must pass for the mailbox domain.
- Queue gate must be clear after controlled outbound tests unless the test explicitly records retry/bounce behavior.
- SPF and DMARC evidence must be recorded for the controlled domain before external beta use.
- Deliverability evidence must record SPF alignment, DMARC alignment, DKIM alignment, queue review, bounce/retry review, and zero known abuse complaints for the controlled beta domain.
- Generate credential-free deliverability evidence with `scripts/collect_deliverability_evidence.py` from controlled mail-flow and queue artifacts after SPF, DMARC, bounce/retry, and abuse review.
- Abuse and deliverability evidence must be recorded in the planning lane before public release.
