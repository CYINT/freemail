# Security Policy

FreeMail is early-stage infrastructure software. Treat deployments as private test systems until release gates explicitly say otherwise.

## Reporting

Report vulnerabilities through the GitHub security advisory flow for `CYINT/freemail` when available. If that is unavailable, contact the maintainers through the CYINT project channel.

## Current Security Posture

- No public signup.
- VPN-only deployment target for the current phase.
- Docker ports bind to `127.0.0.1` by default.
- Secrets are environment-managed and ignored by Git.
- Mail-core candidate is not accepted for production until the architecture spike is complete.

## Sensitive Data

Do not publish logs or artifacts containing:

- message bodies
- mailbox exports
- DKIM private keys
- TLS private keys
- admin passwords
- raw tokens
- DNS provider credentials
