# Mobile Release

FreeMail Mobile is an Expo/React Native client that must remain self-hostable and VPN-first. The open-source repository contains source, metadata, and validation gates only. It must not contain Apple certificates, provisioning profiles, Android keystores, store API keys, generated native project directories, or private service credentials.

## Release Invariants

- Product name: `FreeMail`.
- iOS bundle identifier: `technology.cyint.freemail`.
- Android package: `technology.cyint.freemail`.
- Default API base URL: `https://freemail.kuzuryu.ai`.
- License metadata: `AGPL-3.0-or-later`.
- Mobile bearer sessions use `expo-secure-store`.
- The app must not persist mailbox passwords.
- Push-provider delivery is optional and provider-neutral; raw provider tokens must never be stored by the FreeMail API.

## Local Verification

Run these checks before any mobile build drill:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mobile_static.py
Push-Location apps\mobile
npm ci
npm run config:check
npm run native:prebuild:check
npm run typecheck
npm audit --audit-level=moderate
Pop-Location
```

`npm run config:check` runs `expo config --type public` and validates the app metadata that native builds consume. It does not require app-store credentials.
`npm run native:prebuild:check` copies the mobile app into a temporary directory, runs an Android Expo native prebuild, verifies generated identifiers, and removes the temporary native projects when the drill passes.

## Native Build Drill

Use a clean release branch or temporary worktree for native project generation:

```powershell
Push-Location apps\mobile
npm ci
npm run native:prebuild:check
npx expo prebuild --clean --no-install --platform all
npm run config:check
Pop-Location
```

After the drill, remove generated `ios/` and `android/` directories unless the project intentionally moves to checked-in native projects. Do not commit generated native files as incidental build output.

The repository includes `.github/workflows/mobile-ios-native.yml`, a macOS GitHub Actions workflow that runs the iOS native prebuild drill whenever mobile release surfaces change. Run it manually with `workflow_dispatch` when collecting release evidence for a candidate.

Run the full iOS native drill locally only on a macOS release runner:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mobile_native_prebuild.py --platform ios
```

## Signing Material

Keep signing material outside Git:

- Apple signing certificates and provisioning profiles stay in the Apple Developer account or a private CI secret store.
- Android upload keystores stay in a private password manager or CI secret store.
- Store Connect, Play Console, APNS, FCM, and Expo service tokens stay in repository or organization secrets, never in files.
- Release notes and build provenance may be committed, but credential-bearing screenshots, profiles, and key files may not.

## Private Beta Boundary

Current FreeMail private beta builds must target the VPN hostname and must not expose the API over public internet ingress. Devices used for testing must be enrolled in the private network that can resolve and route `freemail.kuzuryu.ai`.
