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
- `https://freemail.kuzuryu.ai/api/v1/mail-core/readiness` reports SMTP, submission, IMAP, and JMAP readiness

For offline development only, individual external checks can be skipped:

```powershell
.\.venv\Scripts\python.exe scripts\release_gate.py --skip-github-ci --skip-runtime --skip-backup-evidence
```

Do not use skipped gates as release evidence.

## Provenance

Release provenance for a candidate consists of:

- commit SHA
- GitHub Actions run URL for the passing `CI` workflow
- Codecov upload completion in that workflow
- release-gate JSON output
- metadata backup path and checksum, stored outside Git
- mail-store backup path and checksum, stored outside Git
- deployment hostname and exposure boundary evidence

Record this evidence in the planning lane before private-beta use.
