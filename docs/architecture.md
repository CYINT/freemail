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
- Compose mounts Stalwart's config at `/etc/stalwart/config.json` and persists Stalwart data at `/var/lib/stalwart`.
- Stalwart reports healthy after first boot.
- The configured Stalwart profile starts protocol listeners for SMTP, implicit-TLS submission, implicit-TLS IMAP, and JMAP/admin.
- `scripts/qa_mail_core.py --strict` distinguishes TCP reachability from protocol readiness and passes only when all expected protocol surfaces respond.
- `scripts/qa_mail_flow.py` proves actual SMTP receive, authenticated submission, DKIM signing for the mailbox domain, and IMAP message access for a provisioned mailbox. Stalwart's default spam posture can file unauthenticated inbound mail into `Junk Mail`, so the smoke searches all selectable IMAP folders.
- `scripts/qa_stalwart_queue.py` inspects Stalwart `QueuedMessage` state through the official CLI container. It deliberately uses local Stalwart CLI environment variables instead of FreeMail API configuration so mail-server administrator credentials are not wired into the public API container.

Remaining spike work:

- configure one controlled production domain and mailbox
- finish the production spam/deliverability policy beyond the baseline in `docs/deliverability-abuse-policy.md` before private beta
- move from disposable `example.com` smoke metadata to a controlled production test domain
- exercise outbound retry and bounce behavior against a controlled external target and record queue evidence with `scripts/qa_stalwart_queue.py`

## Stalwart Provisioning Plan

FreeMail exports Stalwart `apply` NDJSON through `scripts/export_stalwart_apply_plan.py`. The exporter emits idempotent domain, DKIM signature, and account operations from the FreeMail metadata store. FreeMail one-to-one aliases are provisioned as account aliases.

The exporter intentionally requires a separate ignored secrets JSON file for account secrets. FreeMail stores password hashes only, so it cannot derive plaintext mail-core credentials from the admin database.

The exported plan uses Stalwart CLI upsert operations grouped by object type. It is intended to run after Stalwart's initial `Bootstrap` singleton has been completed; while the server remains in bootstrap mode, Stalwart rejects all object access except `Bootstrap`.

The exporter currently matches DKIM signatures by selector to avoid duplicate signatures on repeated `apply` runs with the current Stalwart CLI. Operators should use unique selectors per hosted domain until reference-based matching on `DkimSignature.domainId` is proven reliable across supported Stalwart versions.

## Mobile Client

`apps/mobile` is the iOS/Android client lane. It uses Expo/React Native and the same bearer-session mailbox APIs as the webmail preview.

The current mobile foundation covers:

- VPN-only default API target at `https://freemail.kuzuryu.ai`
- mailbox session creation and revocation
- SecureStore-backed bearer-session persistence
- inbox snapshot, message read, and compose/send API calls
- static QA that forbids provider trade-dress references and insecure browser-style credential storage

Native build, app-store signing, push notifications, offline cache, attachment UX, and folder/search/contacts screens remain future mobile milestones.
