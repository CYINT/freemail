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

Current progress: persistent token-gated APIs exist for administrator bootstrap, domains, invite-created users, mailboxes, aliases, DKIM keys, generated MX/SPF/DKIM/DMARC DNS guidance, and audit logs. The remaining work is production auth/session integration and mail-core synchronization.

## M3 - Webmail MVP

- Inbox, message read, compose, reply, forward.
- Attachments.
- Responsive UI.
- Browser QA.

Current progress: static webmail preview shell exists with inbox, message reader, compose, folder navigation, responsive CSS, and Python static QA. A first read-only mailbox snapshot API can list IMAP folders and message headers using per-request mailbox credentials, and the webmail preview can load that snapshot from the split frontend/backend over scoped loopback CORS without storing mailbox passwords. Remaining work is authenticated web sessions plus live compose/reply/forward/attachment integration.

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
