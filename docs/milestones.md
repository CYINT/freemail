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

Current progress: persistent APIs exist for administrator bootstrap, admin email/password bearer sessions, authenticator-app MFA setup and login enforcement, static admin-token fallback, owner/admin/operator/auditor permissions, domains, invite-created users, user-password rotation, mailboxes, optional mailbox quota metadata, aliases, DKIM keys, generated MX/SPF/DKIM/DMARC DNS guidance, audit logs, and a secret-free Stalwart sync-plan status endpoint. Bootstrap and user creation accept one-time initial passwords and hash them server-side with Argon2id before storage. Admin password login verifies active administrators against those hashes, enforces TOTP when enabled, stores only hashed bearer sessions, and rejects suspended admins. Password rotation updates the stored FreeMail identity hash, revokes existing admin sessions for the target user, and records an audit event while keeping Stalwart/mail-core account secrets in the ignored operator secret file. The webmail preview now includes an admin console for bootstrap, admin sign-in, MFA setup, role-scoped user invitation, password rotation, domain, user, mailbox, mailbox quota, alias, DKIM, DNS-guidance, mail-core sync-status, suspension/reactivation, and audit-log workflows. Private-beta gates now require credential-free mail-core apply evidence after controlled-domain provisioning, and `scripts/collect_stalwart_apply_evidence.py` generates that evidence from the Stalwart apply workflow. The remaining work is collecting live mail-core apply evidence from the controlled environment.

## M3 - Webmail MVP

- Inbox, message read, compose, reply, forward.
- Attachments.
- Responsive UI.
- Browser QA.

Current progress: static webmail preview shell exists with inbox, message reader, compose, folder navigation, folder management and empty-folder controls, paginated search, thread-aware conversation lookup, saved and extracted contacts, mailbox preferences/signature controls, an operator admin console, responsive CSS, Python static QA, and browser screenshot QA across desktop, tablet, and mobile viewports. A first read-only mailbox snapshot API can list IMAP folders and message headers using per-request mailbox credentials, returns `offset`/`nextOffset`/`hasMore` pagination metadata plus derived `threadId`/`threadSubject`/`inReplyTo` metadata, a thread lookup API can load messages in the same derived conversation within a folder, a message detail API can read selected plain-text message bodies, thread metadata, attachment metadata, and header inspection, and the webmail preview can load those live reads from the split frontend/backend over scoped loopback CORS. A mailbox session API exchanges the mailbox password for a bearer token, stores only encrypted session material server-side, and lets the browser persist only the bearer token. The mailbox preferences API persists display name and default signature metadata used by webmail and mobile compose flows, and saved contacts are durable mailbox metadata covered by metadata backup/restore. The mailbox send API submits compose messages with optional attachments through authenticated implicit-TLS SMTP and appends accepted outbound messages to `Sent Items`, returning `sentFolder` and `sentFolderSaved` for operator visibility. The draft API appends compose payloads to IMAP `Drafts` without SMTP submission, and Drafts messages can be reopened into compose for editing. Reply and forward now prefill sendable compose drafts from the selected live message, Mark read/unread updates the IMAP `\Seen` flag, Star/Unstar updates the IMAP `\Flagged` flag, Archive moves selected messages into an IMAP `Archive` folder through the API, Delete and Spam move selected messages into `Deleted Items` and `Junk Mail`, the shared bulk API and clients can apply read/unread/star/unstar/archive/spam/delete actions to selected messages, attachment download plus single-message EML import/export are exposed through the mailbox API, folder-scoped search covers sender, recipient, subject, and body text, contacts can be extracted from recent mailbox headers into compose recipients, and custom folders can be created, renamed, deleted, or emptied while Trash/Junk can be emptied without deleting the folder itself. Remaining work is polish from live beta feedback.

## M4 - Deliverability And Abuse Controls

- DKIM signing verified.
- SPF/DMARC posture verified.
- Spam filtering active.
- Outbound throttles.
- Abuse controls.

Current progress: DKIM signing is locally verified in the mail-flow smoke for the provisioned mailbox domain, Stalwart queue inspection exists through a local-only CLI gate, the admin API can verify observed MX/SPF/DMARC/DKIM records against generated DNS guidance, `scripts/collect_controlled_domain_evidence.py` can collect credential-free observed DNS, mail-flow, queue, and deliverability evidence into the private-beta packet, `scripts/collect_deliverability_evidence.py` can generate credential-free deliverability evidence from controlled mail-flow and queue artifacts plus SPF/DMARC/bounce/abuse review assertions, `docs/deliverability-abuse-policy.md` captures the private-beta baseline policy, and the mailbox send API now enforces configurable per-mailbox outbound message and recipient caps before SMTP submission. Optional mailbox quota metadata is stored in admin metadata, backed up/restored, shown in the admin console, and summarized in mail-core sync-plan status. Accepted sends are recorded in the API database after SMTP accepts the message. Remaining work is running the controlled-domain collector against real DNS/mail flow and recording final private-beta deliverability evidence.

## M5 - Backup, Restore, Upgrade, And Release Gates

- Backup and restore for metadata, mail store, attachments, and key material.
- Upgrade guide.
- Release provenance.
- Automated release gates, including required CI step provenance.

Current progress: API metadata export and restore tooling exists for domains, users, mailboxes, aliases, DKIM keys, audit logs, mailbox preferences/signatures, and saved contacts. The backup format intentionally excludes admin bearer sessions, browser mailbox sessions, outbound rate-limit counters, and push runtime tables, and the restore path refuses to replace existing metadata unless forced. Mail-store archive and restore scripts now cover the Stalwart Docker volume through a helper container, require explicit restore force, and document drill-volume validation before active-volume replacement. `scripts/collect_backup_evidence.py` collects metadata and mail-store release-packet artifacts plus checksum manifest into an ignored backup directory. `scripts/collect_restore_drill_evidence.py` restores those artifacts into an isolated SQLite database and drill Docker volume, verifies Stalwart apply-plan export, and writes credential-free restore-drill evidence. Release packet status now validates restore-drill evidence content before the hard release gate. Release gate tooling now checks clean Git state, remote SHA, GitHub Actions CI for the exact commit, required CI step provenance, Codecov upload completion in that CI run, repository secret scan, direct dependency license-policy scan, Compose config, loopback-only Compose bindings, backup and restore-drill evidence, release-notes evidence, VPN-only health with exact candidate commit, deployment metadata, and mail-core readiness. Private-beta gate tooling now records runtime boundary, controlled-domain DNS posture evidence, mail-flow, queue, mail-core apply, deliverability/abuse, backup, restore-drill, and decision-owner acceptance checks; `scripts/collect_controlled_domain_evidence.py` reduces packet assembly for the live DNS, mail-flow, queue, and deliverability artifacts. Remaining work is production release-candidate evidence after controlled-domain validation.

## M6 - Private Beta

- Controlled domain deployed.
- VPN/private access boundary accepted.
- External inbound/outbound smoke tests.
- Deliverability evidence recorded.
- Metadata backend decision recorded. SQLite is the only supported backend today; PostgreSQL requires an adapter, migrations, backup/restore coverage, and release-gate evidence before it can be claimed for production/private-beta use.

## M7 - Mobile Client

- iOS and Android client foundation.
- Secure mobile session storage.
- Inbox, read, unread/read-state controls, star controls, bulk message actions, compose, draft saving/editing, reply, forward, archive, spam, delete, search, folders, contacts, and attachments.
- Offline cache and push notification path.

Current progress: Expo/React Native scaffold exists under `apps/mobile` with typed mailbox API client, SecureStore-backed bearer-session persistence, default VPN hostname `https://freemail.kuzuryu.ai`, inbox/read/mark-read/mark-unread/star/unstar/compose/save-draft/edit-draft/reply/forward/archive/spam/delete/bulk-action/sign-out UI, mailbox preferences and default signature controls, paginated and thread-aware folder/search loading, conversation lookup, folder navigation, folder management, empty-folder controls, folder-scoped search, saved and extracted contacts, message header inspection, single-message EML import/export/share, attachment metadata plus authenticated download/share handling, bounded document-picker compose attachments, shared send API support for Sent Items persistence status, secure offline metadata caching for the last loaded mailbox views, bearer-authenticated push-device registration/list/revoke contracts, provider-neutral push notification queueing, development-provider dispatch, optional credential-backed APNS/FCM adapters with encrypted runtime token storage, AGPL package metadata, Expo config validation, Android native prebuild CI drill, macOS iOS native prebuild workflow, signed-build and store-submission evidence gate, read-only mobile release evidence status helper, native release/signing documentation, and static QA in `scripts/qa_mobile_static.py`. Remaining work is signed native build and store-submission evidence from the private signing/store environments.
