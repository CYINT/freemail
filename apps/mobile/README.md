# FreeMail Mobile

FreeMail Mobile is the iOS and Android client lane for the FreeMail platform. It is an Expo/React Native app scaffold that consumes the same mailbox API used by the webmail client.

The current mobile implementation is a source-level foundation, not a production app-store build. It defines project metadata, API client, secure session storage, and the first mailbox screen flows so contributors can build native UI without inventing new server contracts.

## Scope

- iOS and Android client.
- VPN-only self-hosted API target.
- Secure bearer-session persistence through `expo-secure-store`.
- Paginated and thread-aware inbox snapshot/search, conversation lookup, message read, mailbox preferences/signatures, compose/send with Sent Items persistence status, save draft, reply, forward, mark read/unread, bulk read/star/archive/spam/delete actions, and sign-out workflows.
- Folder navigation plus create, rename, empty, and delete controls for supported folders.
- Folder-scoped search, saved contacts, contacts loaded from mailbox headers, and sender block-rule application for the current folder.
- Header inspection, attachment metadata display, authenticated download/share handling, single-message EML import/export/share, and bounded document-picker compose attachments.
- Secure offline metadata cache for the last loaded folder, messages, and contacts.
- Bearer-authenticated push-device registration, listing, revocation, and delivery-status contract.
- Optional credential-backed APNS/FCM adapters and native release workflows.

## Development

```powershell
cd apps\mobile
npm install
npm run config:check
npm run native:prebuild:check
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

The static gate checks that the mobile client uses provider-neutral FreeMail language, references the expected mailbox API endpoints for sessions, paginated and thread-aware snapshots, paginated search, conversation lookup, saved and extracted contacts, sender rules and current-folder block application, folders, mailbox preferences/signatures, message details, header inspection, message read-state/star-state/archive/move/bulk actions, attachments, EML import/export, push-device registration, send, draft saving, and draft reopen into compose, defaults to the VPN hostname, and does not persist mailbox passwords or bearer sessions in insecure browser-style storage. It also guards the document-picker/base64 compose attachment path plus the authenticated attachment download/share path. The offline cache stores mailbox metadata only and the static gate fails if credential markers are added to that cache path.

Push-provider delivery is provider-neutral at this stage. The mobile client can register and revoke a provider token through the FreeMail API, send a push test, and read recent notification delivery status. The API stores a hashed provider token for lookup and stores encrypted runtime token material only when `FREEMAIL_PUSH_TOKEN_SECRET` is configured. `contract-only` and `development` registrations use a deterministic development provider; APNS/FCM delivery runs only when the operator configures the corresponding provider credentials through deployment secrets, otherwise notifications remain queued as `pending_provider`.

## Native Release Readiness

Native releases must follow `docs/mobile-release.md`. The repository intentionally does not contain Apple certificates, provisioning profiles, Android keystores, store API keys, or generated `ios/` and `android/` native projects. Generate native projects only for a release branch or local build drill, then keep signing material outside Git.

`npm run native:prebuild:check` runs the Android native prebuild drill in a temporary copy and verifies generated identifiers without leaving generated native project files in the repository. The repository also includes `.github/workflows/mobile-ios-native.yml` for the macOS iOS native prebuild drill. Run `python ../../scripts/qa_mobile_native_prebuild.py --platform ios` from a macOS release runner for local iOS release evidence.

Signed iOS and Android build artifacts are validated through the root `scripts/mobile_release_gate.py` evidence gate. Keep the evidence JSON and signed artifacts outside Git; the gate accepts only credential-free metadata, artifact hashes, and the VPN-only private beta boundary. Use `--require-store-submission` after TestFlight and Play internal-testing submission evidence exists.
