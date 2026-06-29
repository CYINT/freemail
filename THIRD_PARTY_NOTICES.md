# Third-Party Notices

This file tracks runtime dependencies and infrastructure components considered for FreeMail.

## Runtime Components

| Component | Purpose | License posture | Status |
| --- | --- | --- | --- |
| Python | Admin/runtime API | Python Software Foundation License | Accepted |
| FastAPI | Admin/runtime API framework | MIT | Accepted |
| Uvicorn | ASGI server | BSD-3-Clause | Accepted |
| Pydantic Settings | Environment configuration | MIT | Accepted |
| Stalwart Mail Server | Mail-core candidate | AGPL-3.0 for Community Edition per upstream | Candidate spike |
| PostgreSQL | Metadata store candidate | PostgreSQL License | Planned |
| Caddy | VPN-only HTTPS reverse proxy candidate | Apache-2.0 | Planned |

Before accepting a new runtime dependency, verify AGPL compatibility and update this table.
