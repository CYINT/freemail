# Contributing

FreeMail welcomes focused contributions that advance the AGPL self-hosted mail platform.

## License

FreeMail is licensed under `AGPL-3.0-or-later`. By contributing, you agree that your contribution is provided under that license.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pytest
```

## Required Checks

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m coverage run -m pytest
.\.venv\Scripts\python.exe -m coverage report
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
docker compose config --quiet
docker compose build
```

## Dependency Policy

Use AGPL-compatible dependencies only. Update `THIRD_PARTY_NOTICES.md` when adding runtime components or libraries. Avoid SSPL, BSL, Elastic License, Commons Clause, source-available field-of-use terms, and proprietary spam/reputation feeds unless the project explicitly changes direction.

## Secrets

Do not commit:

- `.env`
- DKIM private keys
- TLS private keys
- mailbox data
- database dumps
- raw access tokens
- provider credentials
- private DNS credentials
