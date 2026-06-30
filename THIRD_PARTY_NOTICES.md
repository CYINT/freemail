# Third-Party Notices

This file tracks runtime dependencies and infrastructure components considered for FreeMail.

## Runtime Components

| Component | Purpose | License posture | Status |
| --- | --- | --- | --- |
| Python | Admin/runtime API | Python Software Foundation License | Accepted |
| argon2-cffi | Server-side administrator and user password hashing | MIT | Accepted |
| cryptography | Session and push-token encryption primitives | Apache-2.0 OR BSD-3-Clause | Accepted |
| dnspython | DNS posture verification | ISC | Accepted |
| email-validator | API email address validation | Unlicense | Accepted |
| FastAPI | Admin/runtime API framework | MIT | Accepted |
| httpx | HTTP client and test client support | BSD-3-Clause | Accepted |
| @expo/vector-icons | Mobile icon set integration | MIT | Accepted |
| expo | Mobile application runtime/tooling | MIT | Accepted |
| expo-document-picker | Mobile attachment selection | MIT | Accepted |
| expo-file-system | Mobile attachment file reads/downloads | MIT | Accepted |
| expo-secure-store | Mobile secure bearer-session storage | MIT | Accepted |
| expo-sharing | Mobile attachment share/save handoff | MIT | Accepted |
| expo-status-bar | Mobile status bar integration | MIT | Accepted |
| React | Mobile UI framework | MIT | Accepted |
| react-native | Mobile native UI runtime | MIT | Accepted |
| Uvicorn | ASGI server | BSD-3-Clause | Accepted |
| pydantic-settings | Environment configuration | MIT | Accepted |
| Stalwart Mail Server | Mail-core candidate | AGPL-3.0 for Community Edition per upstream | Candidate spike |
| PostgreSQL | Metadata store candidate | PostgreSQL License | Planned |
| Caddy | VPN-only HTTPS reverse proxy candidate | Apache-2.0 | Planned |

Before accepting a new runtime dependency, verify AGPL compatibility and update this table.
