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

Current progress: persistent APIs exist for administrator bootstrap, admin email/password bearer sessions, static admin-token fallback, owner/admin/operator/auditor permissions, domains, invite-created users, mailboxes, aliases, DKIM keys, generated MX/SPF/DKIM/DMARC DNS guidance, audit logs, and a secret-free Stalwart sync-plan status endpoint. Bootstrap and user creation accept one-time initial passwords and hash them server-side with Argon2id before storage. Admin password login verifies active administrators against those hashes, stores only hashed bearer sessions, and rejects suspended admins. The webmail preview now includes an admin console for bootstrap, admin sign-in, role-scoped user invitation, domain, user, mailbox, alias, DKIM, DNS-guidance, mail-core sync-status, suspension/reactivation, and audit-log workflows. Private-beta gates now require credential-free mail-core apply evidence after controlled-domain provisioning, and `scripts/collect_stalwart_apply_evidence.py` generates that evidence from the Stalwart apply workflow. The remaining work is collecting live mail-core apply evidence from the controlled environment.

## M3 - Webmail MVP

- Inbox, message read, compose, reply, forward.
- Attachments.
- Responsive UI.
- Browser QA.

Current progress: static webmail preview shell exists with inbox, message reader, compose, folder navigation, folder management controls, search, a contacts panel, an operator admin console, responsive CSS, Python static QA, and browser screenshot QA across desktop, tablet, and mobile viewports. A first read-only mailbox snapshot API can list IMAP folders and message headers using per-request mailbox credentials, a message detail API can read selected plain-text message bodies and attachment metadata, and the webmail preview can load those live reads from the split frontend/backend over scoped loopback CORS. A mailbox session API exchanges the mailbox password for a bearer token, stores only encrypted session material server-side, and lets the browser persist only the bearer token. The mailbox send API submits compose messages with optional attachments through authenticated implicit-TLS SMTP. Reply and forward now prefill sendable compose drafts from the selected live message, Archive moves selected messages into an IMAP `Archive` folder through the API, Delete and Spam move selected messages into `Deleted Items` and `Junk Mail`, attachment download is exposed through the mailbox API, folder-scoped search covers sender, recipient, subject, and body text, contacts can be extracted from recent mailbox headers into compose recipients, and custom folders can be created, renamed, and deleted. Remaining work is polish from live beta feedback.

## M4 - Deliverability And Abuse Controls

- DKIM signing verified.
- SPF/DMARC posture verified.
- Spam filtering active.
- Outbound throttles.
- Abuse controls.

Current progress: DKIM signing is locally verified in the mail-flow smoke for the provisioned mailbox domain, Stalwart queue inspection exists through a local-only CLI gate, the admin API can verify observed MX/SPF/DMARC/DKIM records against generated DNS guidance, `docs/deliverability-abuse-policy.md` captures the private-beta baseline policy, and the mailbox send API now enforces configurable per-mailbox outbound message and recipient caps before SMTP submission. Accepted sends are recorded in the API database after SMTP accepts the message. Remaining work is controlled production-domain SPF/DMARC verification against real DNS, bounce/reputation handling, and private-beta deliverability evidence.

## M5 - Backup, Restore, Upgrade, And Release Gates

- Backup and restore for metadata, mail store, attachments, and key material.
- Upgrade guide.
- Release provenance.
- Automated release gates.

Current progress: API metadata export and restore tooling exists for domains, users, mailboxes, aliases, DKIM keys, and audit logs. The backup format intentionally excludes admin bearer sessions, browser mailbox sessions, outbound rate-limit counters, and push runtime tables, and the restore path refuses to replace existing metadata unless forced. Mail-store archive and restore scripts now cover the Stalwart Docker volume through a helper container, require explicit restore force, and document drill-volume validation before active-volume replacement. Release gate tooling now checks clean Git state, remote SHA, GitHub Actions CI for the exact commit, repository secret scan, direct dependency license-policy scan, Compose config, loopback-only Compose bindings, backup evidence, release-notes evidence, VPN-only health/deployment metadata, and mail-core readiness. Private-beta gate tooling now records runtime boundary, controlled-domain DNS posture evidence, mail-flow, queue, mail-core apply, deliverability/abuse, backup, and decision-owner acceptance checks. Remaining work is production release-candidate evidence after controlled-domain validation.

## M6 - Private Beta

- Controlled domain deployed.
- VPN/private access boundary accepted.
- External inbound/outbound smoke tests.
- Deliverability evidence recorded.
- Metadata backend decision recorded. SQLite is the only supported backend today; PostgreSQL requires an adapter, migrations, backup/restore coverage, and release-gate evidence before it can be claimed for production/private-beta use.

## M7 - Mobile Client

- iOS and Android client foundation.
- Secure mobile session storage.
- Inbox, read, compose, reply, forward, search, folders, contacts, and attachments.
- Offline cache and push notification path.

Current progress: Expo/React Native scaffold exists under `apps/mobile` with typed mailbox API client, SecureStore-backed bearer-session persistence, default VPN hostname `https://freemail.kuzuryu.ai`, inbox/read/compose/reply/forward/sign-out UI, folder navigation and management, folder-scoped search, contacts, attachment metadata plus authenticated download/share handling, bounded document-picker compose attachments, secure offline metadata caching for the last loaded mailbox views, bearer-authenticated push-device registration/list/revoke contracts, provider-neutral push notification queueing, development-provider dispatch, optional credential-backed APNS/FCM adapters with encrypted runtime token storage, AGPL package metadata, Expo config validation, Android native prebuild CI drill, macOS iOS native prebuild workflow, signed-build and store-submission evidence gate, native release/signing documentation, and static QA in `scripts/qa_mobile_static.py`. Remaining work is signed native build and store-submission evidence from the private signing/store environments.
