# Upgrade Guide

FreeMail is pre-1.0. Treat every upgrade as a controlled maintenance event.

## Before Upgrade

1. Confirm the target commit has passed GitHub Actions CI.
2. Keep the stack VPN-only; do not add public ingress during upgrade work.
3. Export metadata:

```powershell
.\.venv\Scripts\python.exe scripts\backup_metadata.py --database data\freemail.sqlite --output .freemail-qa\backups\metadata.json
```

4. Stop mail-core and archive the Stalwart volume:

```powershell
docker inspect freemail-mail-core-1 --format '{{json .Mounts}}'
docker compose --profile mail-core stop mail-core
.\.venv\Scripts\python.exe scripts\backup_mail_store.py --volume freemail_freemail_stalwart --output .freemail-qa\backups\stalwart-mail-store.tar.gz
```

5. Restart mail-core if the upgrade is not immediate:

```powershell
docker compose --profile mail-core up -d mail-core
```

## Upgrade

```powershell
git fetch origin
git checkout main
git pull --ff-only origin main
docker compose --profile web --profile mail-core up --build -d
```

Set release metadata in the runtime environment when deploying a tagged candidate:

```powershell
$env:FREEMAIL_RELEASE_VERSION='0.1.0-dev'
$env:FREEMAIL_RELEASE_COMMIT=(git rev-parse HEAD)
```

## Verify

```powershell
.\.venv\Scripts\python.exe scripts\qa_mail_core.py --strict
Invoke-RestMethod https://freemail.kuzuryu.ai/health
Invoke-RestMethod https://freemail.kuzuryu.ai/api/v1/mail-core/readiness
.\.venv\Scripts\python.exe scripts\create_release_evidence_manifest.py `
  --output .freemail-qa\release\release-evidence-manifest.json `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz `
  --restore-drill-evidence .freemail-qa\backups\restore-drill-evidence.json `
  --mobile-release-evidence .freemail-qa\mobile-release-evidence.json `
  --require-mobile-store-submission `
  --private-beta-evidence .freemail-qa\private-beta-gate-example.com.json `
  --release-notes docs\release-notes\v0.1.0-private-beta.md `
  --release-version v0.1.0-private-beta
.\.venv\Scripts\python.exe scripts\release_packet_status.py `
  --manifest .freemail-qa\release\release-evidence-manifest.json
.\.venv\Scripts\python.exe scripts\release_gate.py `
  --manifest .freemail-qa\release\release-evidence-manifest.json
```

## Rollback

1. Stop mail-core and the API:

```powershell
docker compose --profile web --profile mail-core stop
```

2. Restore metadata only after preserving the current database:

```powershell
Copy-Item data\freemail.sqlite .freemail-qa\backups\freemail-before-rollback.sqlite
.\.venv\Scripts\python.exe scripts\restore_metadata.py --database data\freemail.sqlite --input .freemail-qa\backups\metadata.json --force
```

3. Restore the Stalwart volume only after preserving the current active volume:

```powershell
.\.venv\Scripts\python.exe scripts\backup_mail_store.py --volume freemail_freemail_stalwart --output .freemail-qa\backups\stalwart-mail-store-before-rollback.tar.gz
.\.venv\Scripts\python.exe scripts\restore_mail_store.py --volume freemail_freemail_stalwart --input .freemail-qa\backups\stalwart-mail-store.tar.gz --force
```

4. Start the previous known-good commit and rerun release gates.
