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

- A FastAPI admin/runtime API skeleton.
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

## Docker

The default stack binds to loopback only:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

The mail-core spike profile starts the Stalwart candidate with ports still bound to loopback:

```powershell
docker compose --profile mail-core up --build -d
```

Do not publish FreeMail directly to the public internet during the current phase. Local deployment target is `freemail.kuzuryu.ai` over the private Dragonscale/VPN path only.

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
