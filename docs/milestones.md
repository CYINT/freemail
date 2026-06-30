# Milestones

## M0 - Planning, Repo, And Legal Baseline

- CYINT-owned implementation repo.
- AGPL detected by GitHub.
- Public-safe README and contribution docs.
- CI with lint/test/audit/build gates.

## M1 - Mail-Core Spike

- Stalwart candidate starts locally.
- One domain and one mailbox are configured through the persistent admin API.
- Inbound SMTP receive works.
- Authenticated submission works.
- IMAP or JMAP access is proven.

## M2 - Admin And Domain Operations

- Administrator bootstrap.
- Users, domains, mailboxes, aliases, and DKIM keys.
- DNS guidance for MX, SPF, DKIM, and DMARC.
- Audit logs.

Current progress: persistent token-gated APIs exist for domains, invite-created users, mailboxes, aliases, and audit logs. DKIM and DNS guidance are still pending.

## M3 - Webmail MVP

- Inbox, message read, compose, reply, forward.
- Attachments.
- Responsive UI.
- Browser QA.

## M4 - Deliverability And Abuse Controls

- DKIM signing verified.
- SPF/DMARC posture verified.
- Spam filtering active.
- Outbound throttles.
- Abuse controls.

## M5 - Backup, Restore, Upgrade, And Release Gates

- Backup and restore for metadata, mail store, attachments, and key material.
- Upgrade guide.
- Release provenance.
- Automated release gates.

## M6 - Private Beta

- Controlled domain deployed.
- VPN/private access boundary accepted.
- External inbound/outbound smoke tests.
- Deliverability evidence recorded.
