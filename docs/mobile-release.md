# Mobile Release

FreeMail Mobile is an Expo/React Native client that must remain self-hostable and VPN-first. The open-source repository contains source, metadata, and validation gates only. It must not contain Apple certificates, provisioning profiles, Android keystores, store API keys, generated native project directories, or private service credentials.

## Release Invariants

- Product name: `FreeMail`.
- iOS bundle identifier: `technology.cyint.freemail`.
- Android package: `technology.cyint.freemail`.
- Default API base URL: `https://freemail.kuzuryu.ai`.
- Hosted app-link association paths: `/.well-known/apple-app-site-association` and `/.well-known/assetlinks.json`.
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

The committed `apps/mobile/eas.json` is credential-free release metadata. It defines `development`, `private-beta`, and `production` build and submit profiles, keeps all profiles pointed at `https://freemail.kuzuryu.ai`, uses `internal` distribution for private beta, produces Android `app-bundle` artifacts, and leaves signing credentials to the private EAS or CI environment. Static mobile QA validates these invariants.

Before signed private-beta builds are used for HTTPS invite-link testing, configure the deployment with the public association identifiers:

```powershell
FREEMAIL_MOBILE_IOS_TEAM_ID=<10-character Apple Team ID>
FREEMAIL_MOBILE_IOS_BUNDLE_ID=technology.cyint.freemail
FREEMAIL_MOBILE_ANDROID_PACKAGE=technology.cyint.freemail
FREEMAIL_MOBILE_ANDROID_SHA256_CERT_FINGERPRINTS=<Android signing cert SHA-256 fingerprint>
```

These values are public metadata consumed by Apple and Android app-link verification. They are not a substitute for signing material, and they must not be confused with Apple certificates, provisioning profiles, Android keystores, store API keys, service-account JSON, passwords, private keys, or raw tokens. Until the identifiers are configured, the association endpoints return `503` by design.

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

When using EAS in the private signing environment, run builds from the mobile app directory and keep EAS credentials in the EAS account or CI secret store:

```powershell
Push-Location apps\mobile
npx eas build --platform ios --profile private-beta
npx eas build --platform android --profile private-beta
Pop-Location
```

The EAS build result is not release evidence by itself. After each signed build, use `scripts\collect_mobile_build_evidence.py` to record credential-free artifact provenance and then validate it with `scripts\mobile_release_status.py`.

## Signing Material

Keep signing material outside Git:

- Apple signing certificates and provisioning profiles stay in the Apple Developer account or a private CI secret store.
- Android upload keystores stay in a private password manager or CI secret store.
- Store Connect, Play Console, APNS, FCM, and Expo service tokens stay in repository or organization secrets, never in files.
- Release notes and build provenance may be committed, but credential-bearing screenshots, profiles, and key files may not.

## Signed Build Evidence

This is the mobile signed-build, store-submission, and real-device validation evidence gate for private beta and store-candidate builds. The gate output records the mobile evidence JSON path, byte count, and SHA-256 checksum.

After signed iOS and Android builds complete in the private signing environment, capture a credential-free JSON evidence file outside Git and validate it with:

```powershell
.\.venv\Scripts\python.exe scripts\mobile_release_gate.py --evidence .freemail-qa\mobile-release-evidence.json
```

Create a draft evidence file before the signing run so the required fields are explicit:

```powershell
.\.venv\Scripts\python.exe scripts\create_mobile_release_evidence_template.py `
  --output .freemail-qa\mobile-release-evidence.json
```

The generated file is a credential-free draft. It intentionally keeps `signed`, `submitted`, and device `tested` values false, artifact hashes empty, artifact byte counts zero, and evidence URLs empty until real signed-build, store-submission, and device-validation evidence is recorded.

Inspect the evidence packet before using it in a release candidate:

```powershell
.\.venv\Scripts\python.exe scripts\mobile_release_status.py --evidence .freemail-qa\mobile-release-evidence.json --require-store-submission
```

The status command is read-only. It reports the evidence file path, checksum, failed mobile-release checks, and whether the packet is ready for the hard release gate. It does not run native builds, access app-store APIs, sign artifacts, or connect to real devices.

After each signed build completes in the private signing environment, update the credential-free `builds` section through the collector:

```powershell
.\.venv\Scripts\python.exe scripts\collect_mobile_build_evidence.py `
  --evidence .freemail-qa\mobile-release-evidence.json `
  --platform ios `
  --signed `
  --build-url "https://example.invalid/ios-build" `
  --artifact-type ipa `
  --artifact-bytes 123 `
  --artifact-sha256 "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

.\.venv\Scripts\python.exe scripts\collect_mobile_build_evidence.py `
  --evidence .freemail-qa\mobile-release-evidence.json `
  --platform android `
  --signed `
  --build-url "https://example.invalid/android-build" `
  --artifact-type aab `
  --artifact-bytes 456 `
  --artifact-sha256 "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
```

The signed-build collector exits nonzero unless the platform build record is complete. It records only artifact type, byte count, SHA-256, distribution, and a credential-free HTTPS provenance URL; never pass keystores, provisioning profiles, signing passwords, certificates, raw Expo credentials, or private CI logs.

After each real-device private-beta test, update the credential-free `deviceValidation` section through the collector instead of hand-editing JSON:

```powershell
.\.venv\Scripts\python.exe scripts\collect_mobile_device_validation.py `
  --evidence .freemail-qa\mobile-release-evidence.json `
  --platform ios `
  --tester "release operator" `
  --device-model "iPhone 15" `
  --os-version "iOS 18" `
  --evidence-url "https://example.invalid/ios-device-validation" `
  --tested `
  --tested-at "2026-06-30T00:00:00Z" `
  --all-checks-passed

.\.venv\Scripts\python.exe scripts\collect_mobile_device_validation.py `
  --evidence .freemail-qa\mobile-release-evidence.json `
  --platform android `
  --tester "release operator" `
  --device-model "Pixel 8" `
  --os-version "Android 15" `
  --evidence-url "https://example.invalid/android-device-validation" `
  --tested `
  --tested-at "2026-06-30T00:00:00Z" `
  --all-checks-passed
```

The collector exits nonzero for partial records. Omit `--all-checks-passed` and provide individual `--passed-check` or `--failed-check` flags when recording an incomplete run for diagnosis; incomplete runs remain failing release evidence.

After TestFlight and Play internal-testing submission, require store submission evidence too:

```powershell
.\.venv\Scripts\python.exe scripts\mobile_release_gate.py --evidence .freemail-qa\mobile-release-evidence.json --require-store-submission
```

Record those store submissions with:

```powershell
.\.venv\Scripts\python.exe scripts\collect_mobile_store_submission.py `
  --evidence .freemail-qa\mobile-release-evidence.json `
  --platform ios `
  --submitted `
  --track testflight `
  --submission-url "https://example.invalid/testflight" `
  --submitted-at "2026-06-30T00:00:00Z" `
  --review-state "processing"

.\.venv\Scripts\python.exe scripts\collect_mobile_store_submission.py `
  --evidence .freemail-qa\mobile-release-evidence.json `
  --platform android `
  --submitted `
  --track internal-testing `
  --submission-url "https://example.invalid/play-internal" `
  --submitted-at "2026-06-30T00:00:00Z" `
  --review-state "draft-release-created"
```

The store-submission collector exits nonzero unless the platform submission record is complete. It records store, identifier, track, submitted timestamp, review state, and a credential-free HTTPS evidence URL; never pass App Store Connect API keys, Play service-account JSON, passwords, private keys, provisioning profiles, keystores, or raw tokens.

The evidence must not include API keys, Apple certificates, provisioning profiles, keystores, passwords, private keys, service-account JSON, or raw tokens. It must include signed build records, store-submission records when `--require-store-submission` is used, real-device validation records for iOS and Android, and the VPN-only private-beta boundary. Build, submission, and device evidence URLs must be HTTPS URLs to credential-free evidence. Store submission `submittedAt` and device validation `testedAt` values must be timezone-aware ISO-8601 timestamps. Artifact `sha256` values must be full 64-character SHA-256 hex strings:

```json
{
  "app": {
    "name": "FreeMail",
    "version": "0.1.0-dev",
    "apiBaseUrl": "https://freemail.kuzuryu.ai"
  },
  "builds": {
    "ios": {
      "identifier": "technology.cyint.freemail",
      "signed": true,
      "distribution": "private-beta",
      "buildUrl": "https://example.invalid/ios-build",
      "artifact": {
        "type": "ipa",
        "bytes": 123,
        "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    },
    "android": {
      "identifier": "technology.cyint.freemail",
      "signed": true,
      "distribution": "private-beta",
      "buildUrl": "https://example.invalid/android-build",
      "artifact": {
        "type": "aab",
        "bytes": 456,
        "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      }
    }
  },
  "storeSubmissions": {
    "ios": {
      "store": "app-store-connect",
      "identifier": "technology.cyint.freemail",
      "track": "testflight",
      "submitted": true,
      "submissionUrl": "https://example.invalid/testflight",
      "submittedAt": "2026-06-30T00:00:00Z",
      "reviewState": "processing"
    },
    "android": {
      "store": "play-console",
      "identifier": "technology.cyint.freemail",
      "track": "internal-testing",
      "submitted": true,
      "submissionUrl": "https://example.invalid/play-internal",
      "submittedAt": "2026-06-30T00:00:00Z",
      "reviewState": "draft-release-created"
    }
  },
  "deviceValidation": {
    "ios": {
      "platform": "ios",
      "tested": true,
      "testedAt": "2026-06-30T00:00:00Z",
      "tester": "release operator",
      "deviceModel": "iPhone 15",
      "osVersion": "iOS 18",
      "appVersion": "0.1.0-dev",
      "hostname": "freemail.kuzuryu.ai",
      "networkBoundary": "Dragonscale/VPN clients only",
      "evidenceUrl": "https://example.invalid/ios-device-validation",
      "checks": [
        {"name": "vpn-dns-resolution", "status": "pass"},
        {"name": "auth-login", "status": "pass"},
        {"name": "inbox-sync", "status": "pass"},
        {"name": "message-read", "status": "pass"},
        {"name": "compose-send", "status": "pass"},
        {"name": "invite-link-open", "status": "pass"},
        {"name": "offline-cache", "status": "pass"}
      ]
    },
    "android": {
      "platform": "android",
      "tested": true,
      "testedAt": "2026-06-30T00:00:00Z",
      "tester": "release operator",
      "deviceModel": "Pixel 8",
      "osVersion": "Android 15",
      "appVersion": "0.1.0-dev",
      "hostname": "freemail.kuzuryu.ai",
      "networkBoundary": "Dragonscale/VPN clients only",
      "evidenceUrl": "https://example.invalid/android-device-validation",
      "checks": [
        {"name": "vpn-dns-resolution", "status": "pass"},
        {"name": "auth-login", "status": "pass"},
        {"name": "inbox-sync", "status": "pass"},
        {"name": "message-read", "status": "pass"},
        {"name": "compose-send", "status": "pass"},
        {"name": "invite-link-open", "status": "pass"},
        {"name": "offline-cache", "status": "pass"}
      ]
    }
  },
  "privateBetaBoundary": {
    "hostname": "freemail.kuzuryu.ai",
    "vpnOnly": true,
    "publicInternet": false,
    "requiredBoundary": "Dragonscale/VPN clients only"
  }
}
```

Store submission evidence must be credential-free. It records what was submitted, where, when, and its review state; it must not include App Store Connect API keys, Play service-account JSON, passwords, private keys, provisioning profiles, keystores, or raw tokens.

Real-device validation evidence must also be credential-free. The device validation record stores the platform, tester label, device model, OS version, app version, VPN hostname, evidence URL, and pass/fail results for VPN DNS resolution, auth login, inbox sync, message read, compose/send, HTTPS invite-link app opening, and offline cache behavior. Do not include mailbox passwords, bearer tokens, raw push-provider tokens, profile screenshots containing secrets, or private network configuration exports.

## Private Beta Boundary

Current FreeMail private beta builds must target the VPN hostname and must not expose the API over public internet ingress. Devices used for testing must be enrolled in the private network that can resolve and route `freemail.kuzuryu.ai`.
