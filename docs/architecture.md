# FreeMail Architecture

FreeMail is a product program with multiple deliverables:

- Mail server and mail-core integration.
- Admin API and operational controls.
- Webmail client.
- Mobile client.
- Deployment and release tooling.

## Boundary

The implementation should not become one mail-server blob. Keep the mail-core candidate, admin API, web UI, mobile client, and ops tooling independently testable.

## Admin API And Metadata Store

The admin API owns FreeMail metadata for domains, users, mailboxes, aliases, and audit logs. The current implementation uses SQLite through explicit repository functions so the early product can keep a small dependency surface while still proving persistence and API contracts.

Admin endpoints require the `X-FreeMail-Admin-Token` header and are unavailable until `FREEMAIL_ADMIN_API_TOKEN` is configured. The first-admin bootstrap endpoint separately requires `X-FreeMail-Bootstrap-Token` and refuses to run once an administrator exists. This keeps the open-source default from shipping an active hardcoded credential.

The first persistence boundary is:

- `domains`: hosted domain names and lifecycle status
- `users`: invite-created users with password hashes only
- `mailboxes`: user-owned mailbox addresses under hosted domains
- `aliases`: forwarding aliases
- `dkim_keys`: generated DKIM private keys and public DNS TXT values
- `audit_log`: administrative changes

Future migrations can move this store to PostgreSQL without changing the external API contract.

The current DKIM key surface generates 2048-bit RSA keys and returns the private key only on key creation. List and DNS-guidance responses expose only public DNS material.

## Mail-Core Candidate

The first spike uses Stalwart as the candidate mail-core because its Community Edition is AGPL-aligned and includes modern mail protocols. The spike must prove:

- inbound SMTP receive
- authenticated submission
- IMAP or JMAP mailbox access
- DKIM key handling
- storage and backup posture
- operational configuration model

Postfix, Dovecot, and Rspamd remain fallback candidates if the Stalwart spike fails.

Current spike evidence:

- `docker compose --profile mail-core up -d mail-core` starts the Stalwart candidate.
- Mail-core ports remain host-loopback-bound by Compose.
- Stalwart reports healthy after first boot.
- The first boot enters Stalwart bootstrap/setup mode; this is acceptable for the spike but is not a production-ready mail-domain configuration.
- `scripts/qa_mail_core.py` distinguishes TCP reachability from protocol readiness so bootstrap mode cannot be mistaken for completed SMTP/submission/IMAP proof.

Remaining spike work:

- complete Stalwart initial setup through configuration or API
- configure one controlled domain and mailbox
- prove SMTP receive on the loopback-bound SMTP port
- prove authenticated submission on the loopback-bound submission port
- prove IMAP or JMAP mailbox access
