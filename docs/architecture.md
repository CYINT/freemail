# FreeMail Architecture

FreeMail is a product program with multiple deliverables:

- Mail server and mail-core integration.
- Admin API and operational controls.
- Webmail client.
- Mobile client.
- Deployment and release tooling.

## Boundary

The implementation should not become one mail-server blob. Keep the mail-core candidate, admin API, web UI, mobile client, and ops tooling independently testable.

## Mail-Core Candidate

The first spike uses Stalwart as the candidate mail-core because its Community Edition is AGPL-aligned and includes modern mail protocols. The spike must prove:

- inbound SMTP receive
- authenticated submission
- IMAP or JMAP mailbox access
- DKIM key handling
- storage and backup posture
- operational configuration model

Postfix, Dovecot, and Rspamd remain fallback candidates if the Stalwart spike fails.
