# FreeMail Architecture

FreeMail is a product program with multiple deliverables:

- Mail server and mail-core integration.
- Admin API and operational controls.
- Webmail client.
- Mobile client.
- Deployment and release tooling.

`GET /api/v1/product/readiness` is the credential-free component-readiness surface for this boundary. It reports evidence-backed statuses for the admin API, mail-core integration, webmail client, and mobile client, plus remaining release evidence blockers. Operators and contributors should use this endpoint for product-state inspection instead of inferring readiness from the terse `/health` component map.

## Boundary

The implementation should not become one mail-server blob. Keep the mail-core candidate, admin API, web UI, mobile client, and ops tooling independently testable.

## Admin API And Metadata Store

The admin API owns FreeMail metadata for domains, users, mailboxes, aliases, and audit logs. The current implementation uses SQLite through explicit repository functions so the early product can keep a small dependency surface while still proving persistence and API contracts.

Admin endpoints accept bearer tokens from `POST /api/v1/admin/session` or the legacy `X-FreeMail-Admin-Token` header. Static admin-token access remains unavailable until `FREEMAIL_ADMIN_API_TOKEN` is configured. The first-admin bootstrap endpoint separately requires `X-FreeMail-Bootstrap-Token` and refuses to run once an administrator exists. This keeps the open-source default from shipping an active hardcoded credential while still supporting day-to-day administrator email/password login after bootstrap.

Admin password login verifies active administrator users against stored Argon2id password hashes, creates a hashed bearer session, and stores no admin password material in runtime session tables. Suspending an administrator prevents existing bearer sessions from resolving because the session lookup rechecks the user record.

Administrator roles are intentionally coarse for private beta. `owner` can perform every admin action, including granting or suspending administrators. `admin` can read admin metadata and invite normal users but cannot grant administrator access. `operator` can read metadata and operate domains, mailboxes, aliases, DKIM keys, DNS verification, and status changes but cannot invite users. `auditor` is read-only.

The first persistence boundary is:

- `domains`: hosted domain names and lifecycle status
- `users`: invite-created users with password hashes and coarse administrator role metadata
- `mailboxes`: user-owned mailbox addresses under hosted domains
- `aliases`: forwarding aliases
- `dkim_keys`: generated DKIM private keys and public DNS TXT values
- `audit_log`: administrative changes
- `admin_sessions`: runtime-only hashed administrator bearer sessions, excluded from metadata backups

Future migrations can move this store to PostgreSQL without changing the external API contract.

### Database Backend Status

SQLite is the only supported FreeMail API metadata backend today. The current code passes `sqlite3.Connection` through the API, backup/restore tooling, session handling, outbound policy, Stalwart export, and tests. Do not present PostgreSQL as supported until those boundaries are moved behind a database adapter and covered by CI.

Runtime metadata readiness is exposed at `/api/v1/metadata/readiness`. The endpoint reports the supported backend (`sqlite`), schema revision, and required table/column checks without returning database paths or secrets. Release and private-beta gates require this endpoint to be ready before a candidate can be accepted.

PostgreSQL readiness requires:

- a configured database URL setting that does not break the existing SQLite default
- schema migration tooling that runs against both SQLite development databases and PostgreSQL deployments
- repository functions that avoid SQLite-only row and conflict behavior
- metadata backup/restore coverage against the production backend
- release-gate coverage proving the active backend, migration revision, and backup evidence
- documentation for managed PostgreSQL TLS, credentials, backup retention, and restore drills

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

The admin API exposes `POST /api/v1/admin/mail-core/sync-plan/status` as a secret-free readiness surface for this exporter. It reports domain, DKIM, account, and alias counts plus missing account-secret email addresses based on operator-provided `availableUserSecrets` email names. It does not expose DKIM private keys or account password values.

Private-beta gates require separate credential-free mail-core apply evidence after the Stalwart apply workflow runs. `scripts/collect_stalwart_apply_evidence.py` runs `stalwart-cli apply --stdin`, then records only the controlled domain, operation counts, apply exit code, output hashes, post-apply readiness, and queue-clear status; it must not include raw Stalwart output, credentials, key material, bearer values, or passwords.

The exported plan uses Stalwart CLI upsert operations grouped by object type. It is intended to run after Stalwart's initial `Bootstrap` singleton has been completed; while the server remains in bootstrap mode, Stalwart rejects all object access except `Bootstrap`.

The exporter currently matches DKIM signatures by selector to avoid duplicate signatures on repeated `apply` runs with the current Stalwart CLI. Operators should use unique selectors per hosted domain until reference-based matching on `DkimSignature.domainId` is proven reliable across supported Stalwart versions.

## Mobile Client

`apps/mobile` is the iOS/Android client lane. It uses Expo/React Native and the same bearer-session mailbox APIs as the webmail preview.

The current mobile foundation covers:

- VPN-only default API target at `https://freemail.kuzuryu.ai`
- mailbox session creation and revocation
- SecureStore-backed bearer-session persistence
- inbox snapshot, message read, read/unread and star-state controls, bulk message actions, compose/send, reply, and forward workflows
- folder navigation and non-core folder create/rename/delete controls
- folder-scoped search and contacts
- attachment metadata display and authenticated download/share handling
- bounded document-picker compose attachments encoded for the mailbox send API
- SecureStore-backed offline metadata cache for last loaded folder, message header, and contact snapshots
- bearer-authenticated push-device registration, listing, revocation, notification queueing, deterministic development-provider dispatch, and credential-backed APNS/FCM adapters with hashed plus encrypted runtime token storage
- static QA that forbids provider trade-dress references and insecure browser-style credential storage

Raw and encrypted push-provider tokens are never returned by API responses and are excluded from metadata backups. APNS/FCM dispatch remains disabled until operators configure `FREEMAIL_PUSH_TOKEN_SECRET` plus the corresponding provider credentials in deployment secrets.

Remaining mobile release work is macOS iOS native build-drill evidence, app-store signing, and private-beta device validation.
