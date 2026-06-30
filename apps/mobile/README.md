# FreeMail Mobile

FreeMail Mobile is the iOS and Android client lane for the FreeMail platform. It is an Expo/React Native app scaffold that consumes the same mailbox API used by the webmail client.

The current mobile implementation is a source-level foundation, not a production app-store build. It defines project metadata, API client, secure session storage, and the first mailbox screen flows so contributors can build native UI without inventing new server contracts.

## Scope

- iOS and Android client.
- VPN-only self-hosted API target.
- Secure bearer-session persistence through `expo-secure-store`.
- Inbox snapshot, message read, compose/send, reply, forward, and sign-out workflows.
- Folder navigation plus create, rename, and delete controls for non-core folders.
- Folder-scoped search and contacts loaded from mailbox headers.
- Attachment metadata display with an authenticated attachment availability check.
- Secure offline metadata cache for the last loaded folder, messages, and contacts.
- Future push, richer attachment handling, and native release workflows.

## Development

```powershell
cd apps\mobile
npm install
npm run typecheck
npm audit --audit-level=moderate
npm run start
```

The default API target is:

```text
https://freemail.kuzuryu.ai
```

Devices must be on the Dragonscale/VPN network. Do not point a production mobile build at public internet ingress during the current release phase.

## QA

Static mobile QA runs from the repository root and does not require a native toolchain:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mobile_static.py
```

The static gate checks that the mobile client uses provider-neutral FreeMail language, references the expected mailbox API endpoints for sessions, snapshots, search, contacts, folders, message details, attachments, and send, defaults to the VPN hostname, and does not persist mailbox passwords or bearer sessions in insecure browser-style storage. The offline cache stores mailbox metadata only and the static gate fails if credential markers are added to that cache path.
