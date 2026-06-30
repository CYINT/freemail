# Release Gates

FreeMail release gates are intended for private-beta and later release candidates. They do not make the stack public; the current deployment posture remains VPN-only.

After collecting backups, mobile evidence, private-beta gate output, and release notes, create a top-level release evidence manifest:

```powershell
.\.venv\Scripts\python.exe scripts\create_release_evidence_manifest.py `
  --output .freemail-qa\release\release-evidence-manifest.json `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz `
  --mobile-release-evidence .freemail-qa\mobile-release-evidence.json `
  --require-mobile-store-submission `
  --private-beta-evidence .freemail-qa\private-beta-gate-example.com.json `
  --release-notes docs\release-notes\v0.1.0-private-beta.md `
  --release-version v0.1.0-private-beta
```

The manifest is credential-free. It stores release-packet paths relative to the manifest location when possible, plus the candidate version and mobile store-submission requirement. Keep the evidence files themselves outside Git unless the file is intentionally public, such as release notes.

Before the hard gate, inspect the local release packet without touching Docker, GitHub, or live runtime URLs:

```powershell
.\.venv\Scripts\python.exe scripts\release_packet_status.py `
  --manifest .freemail-qa\release\release-evidence-manifest.json
```

Explicit artifact flags override manifest values when an artifact has been relocated:

```powershell
.\.venv\Scripts\python.exe scripts\release_packet_status.py `
  --manifest .freemail-qa\release\release-evidence-manifest.json `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz `
  --mobile-release-evidence .freemail-qa\mobile-release-evidence.json `
  --require-mobile-store-submission `
  --private-beta-evidence .freemail-qa\private-beta-gate-example.com.json `
  --release-notes docs\release-notes\v0.1.0-private-beta.md `
  --release-version v0.1.0-private-beta
```

The packet status command is read-only. It reports missing, empty, and invalid artifacts, runs the local mobile, private-beta, and release-notes evidence checks, and records SHA-256 checksums for present artifacts. Passing packet status does not replace the full release gate because it intentionally excludes Git, GitHub Actions, Docker Compose, runtime health, deployment-boundary, metadata-readiness, and mail-core-readiness checks.

Mobile release evidence can also be inspected directly before adding it to the release packet:

```powershell
.\.venv\Scripts\python.exe scripts\mobile_release_status.py `
  --evidence .freemail-qa\mobile-release-evidence.json `
  --require-store-submission
```

This mobile status command is read-only and reports missing or failing signed-build and store-submission checks without running native build tools or contacting store APIs.

Run the gate from a clean checkout after pushing the candidate commit to `CYINT/freemail` and after GitHub Actions CI has passed for that exact commit:

```powershell
.\.venv\Scripts\python.exe scripts\release_gate.py `
  --manifest .freemail-qa\release\release-evidence-manifest.json
```

The release gate also accepts explicit artifact flags, which override manifest values:

```powershell
.\.venv\Scripts\python.exe scripts\release_gate.py `
  --manifest .freemail-qa\release\release-evidence-manifest.json `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz `
  --mobile-release-evidence .freemail-qa\mobile-release-evidence.json `
  --require-mobile-store-submission `
  --private-beta-evidence .freemail-qa\private-beta-gate-example.com.json `
  --release-notes docs\release-notes\v0.1.0-private-beta.md `
  --release-version v0.1.0-private-beta
```

The gate verifies:

- clean local Git worktree
- `origin/main` points at the current commit
- GitHub Actions `CI` completed successfully for the current commit
- tracked repository files pass the secret/signing-material scan
- direct runtime dependencies pass the AGPL-compatible license policy scan
- `docker compose config --quiet`
- resolved Compose port bindings for the API, web, and mail-core profiles are loopback-only
- metadata and mail-store backup evidence files exist, are non-empty, and have SHA-256 checksums recorded in the gate output
- mobile signed-build and store-submission evidence passes `scripts/mobile_release_gate.py` with credential-free proof for both iOS and Android
- private-beta gate output passes for at least one controlled domain and includes DNS, mail-flow, queue, mail-core apply, deliverability/abuse, backup, and decision-owner acceptance checks
- release notes exist, are non-empty, include the candidate version, include verification, known-limitations, and VPN-boundary language, contain no placeholder markers, and have a SHA-256 checksum recorded in the gate output
- `https://freemail.kuzuryu.ai/health` reports VPN-only health and release metadata
- `https://freemail.kuzuryu.ai/api/v1/deployment` reports `vpn-only` exposure and `publicInternet: false`
- `https://freemail.kuzuryu.ai/api/v1/metadata/readiness` reports the expected SQLite metadata schema revision and required table/column checks
- `https://freemail.kuzuryu.ai/api/v1/mail-core/readiness` reports SMTP, submission, IMAP, and JMAP readiness

For offline development only, individual external checks can be skipped:

```powershell
.\.venv\Scripts\python.exe scripts\release_gate.py --skip-github-ci --skip-repo-secret-scan --skip-license-policy-scan --skip-runtime --skip-backup-evidence --skip-mobile-evidence --skip-private-beta-evidence --skip-release-notes
```

Do not use skipped gates as release evidence.

## Private-Beta Gate

Before private-beta use, run the private-beta gate. Runtime-only development mode verifies the VPN-only deployment contract and mail-core readiness:

```powershell
.\.venv\Scripts\python.exe scripts\private_beta_gate.py --skip-dns --skip-evidence
```

For a controlled domain, first export DNS guidance from the admin API, capture observed DNS values, run controlled mail-flow and queue checks, apply the Stalwart mail-core plan, collect credential-free apply evidence, collect deliverability/abuse evidence, collect backup evidence, record decision-owner acceptance, then run:

```powershell
.\.venv\Scripts\python.exe scripts\private_beta_gate.py `
  --manifest .freemail-qa\private-beta\private-beta-evidence-manifest.example.com.json `
  --dns-guidance .freemail-qa\dns-guidance-example.com.json `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz
```

Operators can generate a credential-free draft packet with:

```powershell
.\.venv\Scripts\python.exe scripts\create_private_beta_evidence_templates.py `
  --domain example.com `
  --output-dir .freemail-qa\private-beta `
  --decision-owner "Decision Owner"
```

The generated mail-core apply, deliverability, and acceptance templates are intentionally failing drafts until real controlled-domain evidence is filled in.

The generated manifest provides the expected paths for observed DNS, mail-flow, queue, mail-core apply, deliverability, backup, and acceptance evidence. `scripts\private_beta_gate.py --manifest` loads those paths, and any explicit CLI path flag overrides the corresponding manifest entry.

After the controlled mailbox, mailbox-secret JSON, and admin DNS guidance exist, operators can collect the live DNS, mail-flow, queue, and deliverability evidence into the generated packet:

```powershell
.\.venv\Scripts\python.exe scripts\collect_controlled_domain_evidence.py `
  --domain example.com `
  --output-dir .freemail-qa\private-beta `
  --email admin@example.com `
  --secrets-json secrets\mail-core-users.json `
  --dns-guidance .freemail-qa\dns-guidance-example.com.json `
  --spf-aligned `
  --dmarc-aligned `
  --bounce-or-retry-reviewed `
  --abuse-complaints 0 `
  --force
```

The collector runs controlled mail-flow checks, queries the Stalwart queue helper, resolves live DNS from the guidance record names, and writes credential-free JSON only. It intentionally leaves mail-core apply evidence, metadata backup, mail-store backup, and decision-owner acceptance as separate evidence artifacts.

Before running the full private-beta gate, check the packet inventory:

```powershell
.\.venv\Scripts\python.exe scripts\private_beta_packet_status.py `
  --manifest .freemail-qa\private-beta\private-beta-evidence-manifest.example.com.json
```

The packet status command is read-only. It reports missing, empty, and draft-blocking artifacts plus SHA-256 checksums for present files; it does not replace the full private-beta gate.

If observed DNS evidence is omitted from both CLI flags and the manifest, the gate resolves live MX/TXT DNS for the expected record names. The output JSON is release evidence and should be stored outside Git with the other private-beta artifacts. Evidence checks include the path, byte count, and SHA-256 checksum for mail-flow, queue, mail-core apply, deliverability/abuse, backup, and acceptance files.

Mail-flow evidence generated by `scripts\qa_mail_flow.py` must include a timezone-aware ISO-8601 `checkedAt` timestamp.

Generate queue evidence with the Stalwart queue helper after controlled mail-flow tests:

```powershell
.\.venv\Scripts\python.exe scripts\qa_stalwart_queue.py > .freemail-qa\queue-example.com.json
```

The queue JSON must show a clear queue and a timezone-aware ISO-8601 `reviewedAt` timestamp. The private-beta gate accepts the helper output fields `passed`, `clear`, `pending`, `due`, `pendingCount`, `dueCount`, `reviewedAt`, and `messages`; nonzero pending or due counts fail the gate.

Generate mail-core apply evidence with the Stalwart apply collector after the controlled-domain metadata and local secrets file are ready:

```powershell
.\.venv\Scripts\python.exe scripts\collect_stalwart_apply_evidence.py `
  --domain example.com `
  --database data\freemail.sqlite `
  --secrets-json secrets\mail-core-users.json `
  --output .freemail-qa\mail-core-apply-example.com.json
```

The collector runs `stalwart-cli apply --stdin`, probes mail-core readiness, checks queue state, and writes only credential-free hashes, counts, and readiness booleans. Store the JSON output outside Git with the rest of the private-beta evidence packet.

The mail-core apply evidence JSON must be credential-free and include:

```json
{
  "applied": true,
  "appliedAt": "2026-06-30T00:00:00Z",
  "appliedBy": "operator",
  "domain": "example.com",
  "planStatus": {
    "ready": true,
    "operationTypes": ["Domain", "DkimSignature", "Account"],
    "domains": 1,
    "dkimKeys": 1,
    "accounts": 1,
    "aliases": 0,
    "missingProvisioningSecrets": []
  },
  "result": {
    "exitCode": 0,
    "stdoutSha256": "64-character-sha256",
    "stderrSha256": "64-character-sha256"
  },
  "postApplyReadiness": {
    "mailCoreReady": true,
    "queueClear": true
  }
}
```

The gate rejects non-timezone-aware `appliedAt`, domain mismatches, missing domain/account operations, missing provisioning inputs, failed apply exit codes, failed post-apply readiness, uncleared queues, and high-signal sensitive values such as pasted bearer headers, password assignments, API-key assignments, or private-key blocks.

The acceptance JSON must include:

```json
{
  "accepted": true,
  "acceptedAt": "2026-06-30T00:00:00Z",
  "decisionOwner": "CEO",
  "accessBoundary": "Dragonscale/VPN clients only",
  "knownLimitations": ["private beta only"]
}
```

The `acceptedAt` value must be a timezone-aware ISO-8601 timestamp.

The deliverability evidence JSON must include:

```json
{
  "passed": true,
  "domain": "example.com",
  "checkedAt": "2026-06-30T00:00:00Z",
  "spfAligned": true,
  "dmarcAligned": true,
  "dkimAligned": true,
  "queueReviewed": true,
  "bounceOrRetryReviewed": true,
  "abuseComplaints": 0
}
```

The `checkedAt` value must be a timezone-aware ISO-8601 timestamp.

## Provenance

Release provenance for a candidate consists of:

- commit SHA
- GitHub Actions run URL for the passing `CI` workflow
- Codecov upload completion in that workflow
- repository secret/signing-material scan completion in that workflow
- direct runtime dependency license-policy scan completion in that workflow
- release notes path and checksum, committed under `docs/release-notes/`
- release-gate JSON output, including backup, mobile, private-beta, and release-notes SHA-256 checksums
- mobile-release-gate JSON output, including signed-build and store-submission evidence checksums
- private-beta gate JSON output for each controlled domain, including evidence-file SHA-256 checksums
- mail-core apply evidence for each controlled domain, stored outside Git
- deliverability/abuse evidence for each controlled domain
- metadata readiness evidence for the active API database
- metadata backup path and checksum, stored outside Git
- mail-store backup path and checksum, stored outside Git
- deployment hostname and exposure boundary evidence

Record this evidence in the planning lane before private-beta use.
