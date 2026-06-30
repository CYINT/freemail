# Release Gates

FreeMail release gates are intended for private-beta and later release candidates. They do not make the stack public; the current deployment posture remains VPN-only.

Run the gate from a clean checkout after pushing the candidate commit to `CYINT/freemail` and after GitHub Actions CI has passed for that exact commit:

```powershell
.\.venv\Scripts\python.exe scripts\release_gate.py `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz
```

The gate verifies:

- clean local Git worktree
- `origin/main` points at the current commit
- GitHub Actions `CI` completed successfully for the current commit
- `docker compose config --quiet`
- metadata and mail-store backup evidence files exist and are non-empty
- `https://freemail.kuzuryu.ai/health` reports VPN-only health and release metadata
- `https://freemail.kuzuryu.ai/api/v1/deployment` reports `vpn-only` exposure and `publicInternet: false`
- `https://freemail.kuzuryu.ai/api/v1/mail-core/readiness` reports SMTP, submission, IMAP, and JMAP readiness

For offline development only, individual external checks can be skipped:

```powershell
.\.venv\Scripts\python.exe scripts\release_gate.py --skip-github-ci --skip-runtime --skip-backup-evidence
```

Do not use skipped gates as release evidence.

## Private-Beta Gate

Before private-beta use, run the private-beta gate. Runtime-only development mode verifies the VPN-only deployment contract and mail-core readiness:

```powershell
.\.venv\Scripts\python.exe scripts\private_beta_gate.py --skip-dns --skip-evidence
```

For a controlled domain, first export DNS guidance from the admin API, capture observed DNS values, run controlled mail-flow and queue checks, collect backup evidence, record decision-owner acceptance, then run:

```powershell
.\.venv\Scripts\python.exe scripts\private_beta_gate.py `
  --domain example.com `
  --dns-guidance .freemail-qa\dns-guidance-example.com.json `
  --observed-dns .freemail-qa\observed-dns-example.com.json `
  --mail-flow-evidence .freemail-qa\mail-flow-example.com.json `
  --queue-evidence .freemail-qa\queue-example.com.json `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz `
  --acceptance .freemail-qa\private-beta-acceptance-example.com.json
```

If `--observed-dns` is omitted, the gate resolves live MX/TXT DNS for the expected record names. The output JSON is release evidence and should be stored outside Git with the other private-beta artifacts.

The acceptance JSON must include:

```json
{
  "accepted": true,
  "decisionOwner": "CEO",
  "accessBoundary": "Dragonscale/VPN clients only",
  "knownLimitations": ["private beta only"]
}
```

## Provenance

Release provenance for a candidate consists of:

- commit SHA
- GitHub Actions run URL for the passing `CI` workflow
- Codecov upload completion in that workflow
- release-gate JSON output
- private-beta gate JSON output for each controlled domain
- metadata backup path and checksum, stored outside Git
- mail-store backup path and checksum, stored outside Git
- deployment hostname and exposure boundary evidence

Record this evidence in the planning lane before private-beta use.
