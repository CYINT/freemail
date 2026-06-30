# FreeMail

[![CI](https://github.com/CYINT/freemail/actions/workflows/ci.yml/badge.svg)](https://github.com/CYINT/freemail/actions/workflows/ci.yml)

FreeMail is an AGPL open-source mail platform for self-hosted email. The project scope includes mail server operations, webmail, administration, and mobile clients.

FreeMail is not affiliated with Google or any proprietary mail provider. Public project materials should describe FreeMail using its own product language: open-source mail platform, mail server, webmail, mobile mail client, domain administration, and self-hosted operations.

## Scope

The FreeMail program includes:

- Mail server / mail-core integration.
- Inbound SMTP receive.
- Authenticated SMTP submission and outbound delivery.
- IMAP or JMAP mailbox access.
- Admin API for domains, users, mailboxes, aliases, policies, and audit logs.
- Webmail and admin web UI.
- Mobile client lane for iOS/Android.
- DKIM, SPF, DMARC, spam, abuse, and deliverability controls.
- Backup, restore, upgrade, health, release, and deployment gates.

## Current State

This repository is at the implementation baseline. It contains:

- A FastAPI admin/runtime API with persistent SQLite-backed domain, user, mailbox, alias, and audit-log surfaces.
- A static webmail preview shell with inbox, search, message reader, compose, folder navigation, and responsive layout QA.
- An Expo/React Native mobile client scaffold with secure session storage, mailbox workflows, and static QA.
- A Docker Compose stack with VPN-only loopback bindings by default.
- A Stalwart mail-core candidate profile for the first architecture spike.
- CI for linting, tests, repository secret scanning, dependency audit, Compose validation, and image build.

## License

FreeMail is licensed under `AGPL-3.0-or-later`. See `LICENSE`.

## Local Development

Requirements:

- Python 3.13 or newer
- Docker Desktop or Docker Engine

Quick start:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn freemail_api.main:app --app-dir src --reload
```

Then open `http://127.0.0.1:8080/health`.

Run repository hygiene scans before publishing changes:

```powershell
.\.venv\Scripts\python.exe scripts\qa_repo_secrets.py
.\.venv\Scripts\python.exe scripts\qa_license_policy.py
```

## Admin API

Admin endpoints require `X-FreeMail-Admin-Token` and remain disabled until `FREEMAIL_ADMIN_API_TOKEN` is set. Do not commit a real token.

Initial endpoints:

- `POST /api/v1/bootstrap/admin`
- `POST /api/v1/admin/domains`
- `GET /api/v1/admin/domains`
- `PATCH /api/v1/admin/domains/{domainId}/status`
- `POST /api/v1/admin/users`
- `GET /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{userId}/status`
- `POST /api/v1/admin/mailboxes`
- `GET /api/v1/admin/mailboxes`
- `PATCH /api/v1/admin/mailboxes/{mailboxId}/status`
- `POST /api/v1/admin/aliases`
- `GET /api/v1/admin/aliases`
- `PATCH /api/v1/admin/aliases/{aliasId}/status`
- `POST /api/v1/admin/dkim-keys`
- `GET /api/v1/admin/dkim-keys`
- `PATCH /api/v1/admin/dkim-keys/{dkimKeyId}/status`
- `GET /api/v1/admin/domains/{domainId}/dns`
- `POST /api/v1/admin/domains/{domainId}/dns/verify`
- `GET /api/v1/admin/audit-log`

The current metadata store is SQLite at `FREEMAIL_DB_PATH`, defaulting to `data/freemail.sqlite` locally and a Docker volume path in Compose. PostgreSQL is not yet a supported metadata backend; see `docs/architecture.md` for the adapter, migration, backup, and release-gate work required before production/private-beta PostgreSQL use. Mail-store persistence remains part of the Stalwart mail-core spike.

The bootstrap endpoint requires `X-FreeMail-Bootstrap-Token`, refuses to run unless `FREEMAIL_BOOTSTRAP_TOKEN` is configured, and refuses to create a second administrator after the first admin exists.

DNS guidance returns the MX, SPF, DMARC, and DKIM records expected for a domain. The DNS verification endpoint accepts observed DNS values and returns a check list plus a `ready` boolean; it is intended as the repeatable gate before controlled-domain mail-flow tests.

Admin status endpoints support abuse response for private beta. Domains, mailboxes, aliases, and DKIM keys accept `active` or `suspended`; users accept `invited` or `suspended`. Status changes are audit logged, suspended metadata blocks mailbox API access for managed mailboxes, and suspended domains, mailboxes, aliases, and DKIM keys are excluded from DNS guidance and Stalwart apply-plan exports where applicable.

## Docker

The default stack binds to loopback only:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

The static webmail preview can be started with the `web` profile:

```powershell
docker compose --profile web up -d web
.\.venv\Scripts\python.exe scripts\qa_web_static.py
```

Run browser screenshot QA for the webmail shell with:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts\qa_web_browser.py
```

Screenshots are written under the ignored `.freemail-qa\web-screenshots` directory. The browser QA checks desktop, tablet, and mobile viewports for the inbox, reader, compose, and message-action surfaces, and fails on horizontal overflow.

Run mobile static QA with:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mobile_static.py
Push-Location apps\mobile
npm ci
npm run config:check
npm run native:prebuild:check
npm run typecheck
npm audit --audit-level=moderate
Pop-Location
```

The mobile scaffold lives in `apps\mobile`, uses Expo/React Native, defaults to `https://freemail.kuzuryu.ai`, and persists bearer sessions through `expo-secure-store` rather than browser-style storage. It currently covers sign-in, inbox/folder snapshots, message reading, compose/send with bounded document-picker attachments, reply/forward drafts, folder-scoped search, contacts, non-core folder management, attachment metadata plus authenticated download/share handling, secure offline metadata caching for the last loaded mailbox views, bearer-authenticated push-device registration, and provider-neutral push notification delivery status.

Mobile native release posture is documented in `docs\mobile-release.md`. The open-source repo keeps signing credentials, provisioning profiles, keystores, store API keys, and generated native projects out of source control; CI validates the Expo config, Android native prebuild drill, static release checklist, and macOS iOS native prebuild drill.
Signed mobile builds and app-store submission evidence are validated with `scripts\mobile_release_gate.py` from credential-free evidence stored outside Git.
Use `scripts\create_mobile_release_evidence_template.py` to create a failing credential-free draft evidence file before private signing and store-submission runs.

The push contract stores hashed provider tokens for lookup and, when `FREEMAIL_PUSH_TOKEN_SECRET` is configured, stores encrypted provider tokens for runtime dispatch. Raw and encrypted provider tokens are never returned by the API and runtime push tables are excluded from metadata backups. Native clients use stable register/list/revoke plus provider-neutral notification status APIs:

```text
POST /api/v1/mailbox/push/devices
GET /api/v1/mailbox/push/devices
DELETE /api/v1/mailbox/push/devices/{deviceId}
POST /api/v1/mailbox/push/notifications
GET /api/v1/mailbox/push/notifications
```

Push notification dispatch has a deterministic development provider for `contract-only` and `development` registrations. Credential-backed `fcm` and `apns` adapters are available when the operator configures provider secrets through environment variables; otherwise those notifications are recorded as `pending_provider`.

Required FCM settings:

```text
FREEMAIL_PUSH_TOKEN_SECRET=...
FREEMAIL_FCM_PROJECT_ID=...
FREEMAIL_FCM_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

Required APNS settings:

```text
FREEMAIL_PUSH_TOKEN_SECRET=...
FREEMAIL_APNS_TEAM_ID=...
FREEMAIL_APNS_KEY_ID=...
FREEMAIL_APNS_PRIVATE_KEY_PEM=<apns-token-auth-private-key-pem>
FREEMAIL_APNS_BUNDLE_ID=technology.cyint.freemail
FREEMAIL_APNS_USE_SANDBOX=false
```

Keep all provider credentials out of Git and configure them only through deployment secrets.

The webmail preview can load live mailbox folders and message headers from the API. Start `admin-api`, `mail-core`, and `web`, open `http://127.0.0.1:18091`, enter a mailbox address/password, and keep the API field pointed at `http://127.0.0.1:18090`. The browser client exchanges the mailbox password for a bearer session at `POST /api/v1/mailbox/session`, stores only the bearer token in `localStorage`, and revokes it with `DELETE /api/v1/mailbox/session` on sign out. The API stores mailbox passwords only as encrypted session material using `FREEMAIL_SESSION_SECRET`. For a different local web origin, set `FREEMAIL_WEB_CORS_ORIGINS`.

The first read-only mailbox API uses per-request IMAP credentials and does not store mailbox passwords:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mailbox_snapshot_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
.\.venv\Scripts\python.exe scripts\qa_mailbox_message_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
.\.venv\Scripts\python.exe scripts\qa_mailbox_session_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
.\.venv\Scripts\python.exe scripts\qa_mailbox_search_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
.\.venv\Scripts\python.exe scripts\qa_mailbox_contacts_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
.\.venv\Scripts\python.exe scripts\qa_mailbox_folder_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
```

`FREEMAIL_SESSION_SECRET` must be set for browser mailbox sessions. Use a long random value and keep it out of source control. Existing per-request mailbox credential QA scripts remain available for API smoke coverage.

The mailbox search API searches the selected folder by sender, recipient, subject, and body text:

```text
GET /api/v1/mailbox/search?folder=INBOX&query=needle&limit=25
```

The webmail search form uses the current folder and the browser's bearer session.

The contacts API extracts deduplicated contacts from recent `From`, `Reply-To`, `To`, and `Cc` message headers in the selected folder:

```text
GET /api/v1/mailbox/contacts?folder=INBOX&limit=100
```

The webmail contacts panel can load those records from the browser's bearer session and click a contact into the compose recipient field.

Folder management uses the browser bearer session or per-request mailbox credentials:

```text
POST /api/v1/mailbox/folder
PATCH /api/v1/mailbox/folder
DELETE /api/v1/mailbox/folder
```

Create accepts `{ "folder": "Clients" }`, rename accepts `{ "folder": "Clients", "targetFolder": "Customers" }`, and delete accepts `{ "folder": "Customers" }`. The webmail sidebar exposes create, rename-current-folder, and delete-current-folder controls while protecting core folders such as `INBOX`.

The first mailbox send API uses the same per-request credential posture and submits through authenticated implicit-TLS SMTP:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mailbox_send_api.py --email admin@example.com --recipient admin@example.com --secrets-json secrets\mail-core-users.json
```

The current webmail preview supports reply and forward as live compose-prefill workflows from the selected message body; sending those drafts uses the same mailbox send API. The Archive action uses IMAP copy/delete semantics, creates the `Archive` folder if it is missing, and refreshes the current folder after success:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mailbox_archive_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
```

The archive smoke creates and archives its own generated self-addressed message so it does not mutate arbitrary mailbox data.

Delete and spam actions use the generic mailbox move API to copy a selected message into `Deleted Items` or `Junk Mail`, mark the source message deleted, and expunge the source folder:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mailbox_move_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
```

The move smoke creates two generated self-addressed messages, moves one to trash and one to spam, then verifies both generated messages are removed from `INBOX`.

Attachment send/read/download is covered by a generated self-addressed smoke:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mailbox_attachment_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
```

The attachment smoke sends a small text attachment, waits for the generated message, verifies attachment metadata on the message detail API, downloads the attachment through the API, and compares the bytes without printing mailbox secrets.

Outbound attachment submission is bounded by:

- `FREEMAIL_MAX_ATTACHMENT_BYTES`, default `1048576` decoded bytes per attachment.
- `FREEMAIL_ALLOWED_ATTACHMENT_CONTENT_TYPES`, default `text/plain,text/csv,application/pdf,image/png,image/jpeg`.

The API rejects unsupported content types, invalid base64 payloads, and decoded attachments above the configured per-attachment limit before SMTP submission.

Outbound submission is also rate-limited per mailbox before SMTP submission:

- `FREEMAIL_SEND_RATE_WINDOW_SECONDS`, default `3600`.
- `FREEMAIL_SEND_RATE_MAX_MESSAGES`, default `120` accepted sends per window.
- `FREEMAIL_SEND_RATE_MAX_RECIPIENTS`, default `500` accepted recipients per window.

Set either max value to `0` to disable that specific cap. Accepted sends are recorded in the FreeMail API database after SMTP accepts the message; rejected attachments, invalid payloads, and refused SMTP attempts do not consume quota.

The mail-core spike profile starts the Stalwart candidate with ports still bound to loopback:

```powershell
docker compose --profile mail-core up --build -d
.\.venv\Scripts\python.exe scripts\qa_mail_core.py
```

Do not publish FreeMail directly to the public internet during the current phase. Local deployment target is `freemail.kuzuryu.ai` over the private Dragonscale/VPN path only.

The Stalwart profile mounts `ops\stalwart\config.json` at `/etc/stalwart/config.json` and persists mail-core data at `/var/lib/stalwart` in the Compose-managed Stalwart volume. With the default project name in this repo, Docker names that volume `freemail_freemail_stalwart`. The default Stalwart listener set is exposed on loopback as SMTP `2525`, implicit-TLS submission `2465`, implicit-TLS IMAP `2993`, JMAP/admin `18092`, and HTTPS `18443`.

`scripts\qa_mail_core.py` exits successfully when the configured mail-core ports are reachable and reports whether each protocol is actually ready. Add `--strict` when the Stalwart setup is expected to pass SMTP, submission, IMAP, and JMAP checks.

After a domain and mailbox are provisioned into Stalwart, run an end-to-end message smoke:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mail_flow.py --email admin@example.com --secrets-json secrets\mail-core-users.json --inbound-recipient hello@example.com
```

The smoke sends unauthenticated inbound SMTP, sends authenticated submission over implicit TLS, verifies both messages through implicit-TLS IMAP, and requires the submitted message to include a DKIM signature for the mailbox domain. Stalwart's default spam posture may place unauthenticated inbound mail in `Junk Mail`; the smoke searches every selectable IMAP folder and treats that as delivered.

To inspect outbound retry/bounce state during controlled-domain tests, use the Stalwart queue gate with local-only Stalwart admin environment variables:

```powershell
$env:STALWART_URL='http://host.docker.internal:18092'
$env:STALWART_USER='admin'
$env:STALWART_PASSWORD='<local ignored Stalwart recovery/admin password>'
.\.venv\Scripts\python.exe scripts\qa_stalwart_queue.py
```

The queue gate succeeds only when Stalwart reports no pending queued messages. Use `--allow-pending` when intentionally testing retry state and recording queue evidence.

FreeMail can export a Stalwart `apply` plan from admin metadata:

```powershell
.\.venv\Scripts\python.exe scripts\export_stalwart_apply_plan.py --database data\freemail.sqlite --secrets-json secrets\mail-core-users.json > .freemail-qa\stalwart-plan.ndjson
```

Keep `secrets\mail-core-users.json` ignored and local. It maps mailbox email addresses to Stalwart account secrets because FreeMail stores password hashes only and cannot recover user passwords for mail-core provisioning.

The plan is newline-delimited JSON for `stalwart-cli apply`. Stalwart must be taken out of first-boot bootstrap mode before domain, account, or DKIM objects can be applied:

```powershell
docker run --rm -i -e STALWART_URL -e STALWART_USER -e STALWART_PASSWORD ghcr.io/stalwartlabs/cli apply --stdin < .freemail-qa\stalwart-plan.ndjson
```

The exporter matches DKIM signatures by selector to avoid duplicate Stalwart signatures on repeated local applies. Use unique selectors per hosted domain until the Stalwart CLI supports reliable reference-based matching for `DkimSignature` domain IDs.

## Backup And Restore

Read `docs/backup-restore.md` before relying on backups. The metadata backup tools export API metadata, audit logs, and DKIM key material; they intentionally exclude mailbox sessions, outbound rate-limit counters, push-device registrations, and Stalwart mail-store data.

Export metadata:

```powershell
.\.venv\Scripts\python.exe scripts\backup_metadata.py --database data\freemail.sqlite --output .freemail-qa\backups\metadata.json
```

Restore metadata into a new database:

```powershell
.\.venv\Scripts\python.exe scripts\restore_metadata.py --database data\freemail-restored.sqlite --input .freemail-qa\backups\metadata.json
```

Metadata backups include DKIM private keys and password hashes. Store them encrypted and outside the repository.

Mail-store messages, attachments, indexes, and queue state live in the Stalwart Docker volume. Archive that volume only after stopping writers:

```powershell
docker inspect freemail-mail-core-1 --format '{{json .Mounts}}'
docker compose --profile mail-core stop mail-core
.\.venv\Scripts\python.exe scripts\backup_mail_store.py --volume freemail_freemail_stalwart --output .freemail-qa\backups\stalwart-mail-store.tar.gz
docker compose --profile mail-core up -d mail-core
```

Restore drills should target a separate volume before replacing the active Stalwart volume:

```powershell
.\.venv\Scripts\python.exe scripts\restore_mail_store.py --volume freemail_stalwart_restore --input .freemail-qa\backups\stalwart-mail-store.tar.gz --force
```

## Upgrade And Release Gates

Read `docs/upgrade.md` and `docs/release-gates.md` before private-beta upgrades or release-candidate work.

Run the local release gate only after the candidate commit has been pushed and GitHub Actions CI has passed for that exact commit:

```powershell
.\.venv\Scripts\python.exe scripts\release_gate.py `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz `
  --mobile-release-evidence .freemail-qa\mobile-release-evidence.json `
  --require-mobile-store-submission `
  --private-beta-evidence .freemail-qa\private-beta-gate-example.com.json `
  --release-notes docs\release-notes\v0.1.0-private-beta.md `
  --release-version v0.1.0-private-beta
```

The release gate checks clean Git state, remote SHA, GitHub Actions CI, Compose config, backup evidence, mobile signed-build/store-submission evidence, controlled-domain private-beta evidence, release-notes evidence, VPN-only health/deployment metadata, metadata-store readiness, and mail-core protocol readiness.

Run the private-beta runtime gate during development:

```powershell
.\.venv\Scripts\python.exe scripts\private_beta_gate.py --skip-dns --skip-evidence
```

For a real beta domain, pass admin DNS guidance plus observed DNS evidence, mail-flow evidence, queue evidence, backups, and decision-owner acceptance. Omit `--observed-dns` only when the gate should resolve live MX/TXT records:

```powershell
.\.venv\Scripts\python.exe scripts\private_beta_gate.py `
  --domain example.com `
  --dns-guidance .freemail-qa\dns-guidance-example.com.json `
  --observed-dns .freemail-qa\observed-dns-example.com.json `
  --mail-flow-evidence .freemail-qa\mail-flow-example.com.json `
  --queue-evidence .freemail-qa\queue-example.com.json `
  --deliverability-evidence .freemail-qa\deliverability-example.com.json `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz `
  --acceptance .freemail-qa\private-beta-acceptance-example.com.json
```

To avoid hand-authoring the JSON packet, create draft evidence templates first:

```powershell
.\.venv\Scripts\python.exe scripts\create_private_beta_evidence_templates.py `
  --domain example.com `
  --output-dir .freemail-qa\private-beta `
  --decision-owner "Decision Owner"
```

The generated files are credential-free drafts. They intentionally keep `passed` and `accepted` false until controlled-domain DNS, mail flow, queue, deliverability, backup, and owner-review evidence are actually recorded.

Generate queue evidence with `scripts\qa_stalwart_queue.py` after controlled mail-flow tests; the private-beta gate requires a clear queue with zero pending and due messages.

## VPN-Only Deployment

Read `docs/deployment-vpn.md`. The intended local hostname is:

```text
freemail.kuzuryu.ai
```

The app and candidate mail-core ports must remain bound to `127.0.0.1` on the host. A private reverse proxy or bridge may expose HTTPS to Dragonscale/VPN clients only.

## Codecov

CI uploads `coverage.xml` to Codecov when `CODECOV_TOKEN` is configured as a GitHub Actions secret.

## Roadmap

See `docs/milestones.md`.
