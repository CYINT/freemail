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
- A static web shell placeholder.
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

The mail-core spike profile starts the Stalwart candidate with ports still bound to loopback:

```powershell
docker compose --profile mail-core up --build -d
.\.venv\Scripts\python.exe scripts\qa_mail_core.py
```

Do not publish FreeMail directly to the public internet during the current phase. Local deployment target is `freemail.kuzuryu.ai` over the private Dragonscale/VPN path only.

The Stalwart profile mounts `ops\stalwart\config.json` at `/etc/stalwart/config.json` and persists mail-core data in the `freemail_stalwart` Docker volume at `/var/lib/stalwart`. The default Stalwart listener set is exposed on loopback as SMTP `2525`, implicit-TLS submission `2465`, implicit-TLS IMAP `2993`, JMAP/admin `18092`, and HTTPS `18443`.

`scripts\qa_mail_core.py` exits successfully when the configured mail-core ports are reachable and reports whether each protocol is actually ready. Add `--strict` when the Stalwart setup is expected to pass SMTP, submission, IMAP, and JMAP checks.

FreeMail can export a Stalwart `apply` plan from admin metadata:

```powershell
.\.venv\Scripts\python.exe scripts\export_stalwart_apply_plan.py --database data\freemail.sqlite --secrets-json secrets\mail-core-users.json > .freemail-qa\stalwart-plan.ndjson
```

Keep `secrets\mail-core-users.json` ignored and local. It maps mailbox email addresses to Stalwart account secrets because FreeMail stores password hashes only and cannot recover user passwords for mail-core provisioning.

The plan is newline-delimited JSON for `stalwart-cli apply`. Stalwart must be taken out of first-boot bootstrap mode before domain, account, or DKIM objects can be applied:

```powershell
docker run --rm -i -e STALWART_URL -e STALWART_USER -e STALWART_PASSWORD ghcr.io/stalwartlabs/cli apply --stdin < .freemail-qa\stalwart-plan.ndjson
```

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
