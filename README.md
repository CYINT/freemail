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
- A static webmail preview shell with inbox, message reader, compose, folder navigation, and responsive layout QA.
- A mobile client lane placeholder.
- A Docker Compose stack with VPN-only loopback bindings by default.
- A Stalwart mail-core candidate profile for the first architecture spike.
- CI for linting, tests, dependency audit, Compose validation, and image build.

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

## Admin API

Admin endpoints require `X-FreeMail-Admin-Token` and remain disabled until `FREEMAIL_ADMIN_API_TOKEN` is set. Do not commit a real token.

Initial endpoints:

- `POST /api/v1/bootstrap/admin`
- `POST /api/v1/admin/domains`
- `GET /api/v1/admin/domains`
- `POST /api/v1/admin/users`
- `GET /api/v1/admin/users`
- `POST /api/v1/admin/mailboxes`
- `GET /api/v1/admin/mailboxes`
- `POST /api/v1/admin/aliases`
- `GET /api/v1/admin/aliases`
- `POST /api/v1/admin/dkim-keys`
- `GET /api/v1/admin/dkim-keys`
- `GET /api/v1/admin/domains/{domainId}/dns`
- `GET /api/v1/admin/audit-log`

The current metadata store is SQLite at `FREEMAIL_DB_PATH`, defaulting to `data/freemail.sqlite` locally and a Docker volume path in Compose. Mail-store persistence remains part of the Stalwart mail-core spike.

The bootstrap endpoint requires `X-FreeMail-Bootstrap-Token`, refuses to run unless `FREEMAIL_BOOTSTRAP_TOKEN` is configured, and refuses to create a second administrator after the first admin exists.

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

The webmail preview can load live mailbox folders and message headers from the API. Start `admin-api`, `mail-core`, and `web`, open `http://127.0.0.1:18091`, enter a mailbox address/password, and keep the API field pointed at `http://127.0.0.1:18090`. The browser client sends credentials only with the snapshot request and does not use `localStorage`, `sessionStorage`, or cookies for mailbox passwords. For a different local web origin, set `FREEMAIL_WEB_CORS_ORIGINS`.

The first read-only mailbox API uses per-request IMAP credentials and does not store mailbox passwords:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mailbox_snapshot_api.py --email admin@example.com --secrets-json secrets\mail-core-users.json
```

The mail-core spike profile starts the Stalwart candidate with ports still bound to loopback:

```powershell
docker compose --profile mail-core up --build -d
.\.venv\Scripts\python.exe scripts\qa_mail_core.py
```

Do not publish FreeMail directly to the public internet during the current phase. Local deployment target is `freemail.kuzuryu.ai` over the private Dragonscale/VPN path only.

The Stalwart profile mounts `ops\stalwart\config.json` at `/etc/stalwart/config.json` and persists mail-core data in the `freemail_stalwart` Docker volume at `/var/lib/stalwart`. The default Stalwart listener set is exposed on loopback as SMTP `2525`, implicit-TLS submission `2465`, implicit-TLS IMAP `2993`, JMAP/admin `18092`, and HTTPS `18443`.

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

## VPN-Only Deployment

Read `docs/deployment-vpn.md`. The intended local hostname is:

```text
freemail.kuzuryu.ai
```

The app and candidate mail-core ports must remain bound to `127.0.0.1` on the host. A private reverse proxy or bridge may expose HTTPS to Dragonscale/VPN clients only.

## Codecov

CI is ready to upload `coverage.xml` when `CODECOV_TOKEN` is configured as a GitHub Actions secret. Tell the maintainer when a Codecov repository token is available.

## Roadmap

See `docs/milestones.md`.
