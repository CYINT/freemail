# Backup And Restore

FreeMail currently has two persistence surfaces:

- API metadata in SQLite at `FREEMAIL_DB_PATH`.
- Mail-core data in the Docker volume mounted at `/var/lib/stalwart`.

The metadata backup tools cover domains, users, encrypted administrator MFA secrets, mailboxes, aliases, DKIM keys, audit logs, mailbox preferences, saved contacts, and mailbox sender rules. They intentionally exclude admin bearer sessions, browser mailbox sessions, outbound rate-limit counters, push-device registrations, encrypted push-provider tokens, and push-notification delivery records.

Metadata backups include DKIM private keys, encrypted administrator MFA secrets, and password hashes. Treat every backup file as sensitive operational material: encrypt it at rest, keep it out of Git, and restrict access to administrators.

## Release Evidence Collection

For release-candidate evidence, collect the metadata backup and mail-store archive into one ignored directory:

```powershell
docker inspect freemail-mail-core-1 --format '{{json .Mounts}}'
docker compose --profile mail-core stop mail-core
.\.venv\Scripts\python.exe scripts\collect_backup_evidence.py `
  --database data\freemail.sqlite `
  --output-dir .freemail-qa\backups `
  --mail-store-volume freemail_freemail_stalwart `
  --force
docker compose --profile mail-core up -d mail-core
```

The collector writes:

- `metadata.json`: API metadata backup.
- `stalwart-mail-store.tar.gz`: Docker-volume mail-store archive.
- `backup-evidence-manifest.json`: artifact paths, byte counts, and SHA-256 checksums for release-packet wiring.

The manifest records relative release-gate input names, but the backup files themselves remain sensitive because they may include DKIM private keys, password hashes, mailbox contents, attachments, indexes, and queue state.

After collecting backups, run a restore drill into isolated targets:

```powershell
.\.venv\Scripts\python.exe scripts\collect_restore_drill_evidence.py `
  --metadata-backup .freemail-qa\backups\metadata.json `
  --mail-store-backup .freemail-qa\backups\stalwart-mail-store.tar.gz `
  --output .freemail-qa\backups\restore-drill-evidence.json `
  --drill-database .freemail-qa\restore-drill\metadata-restored.sqlite `
  --drill-mail-store-volume freemail_stalwart_restore_drill `
  --force
```

The restore-drill evidence file is credential-free. It records input byte counts and SHA-256 checksums, restored metadata table counts, Stalwart apply-plan export status, and the drill mail-store volume name. It does not embed metadata rows, DKIM private keys, password hashes, or mailbox content.

## Export API Metadata

```powershell
.\.venv\Scripts\python.exe scripts\backup_metadata.py --database data\freemail.sqlite --output .freemail-qa\backups\metadata.json
```

## Restore API Metadata

Restore refuses to overwrite an existing metadata database unless `--force` is explicit.

```powershell
.\.venv\Scripts\python.exe scripts\restore_metadata.py --database data\freemail-restored.sqlite --input .freemail-qa\backups\metadata.json
```

Replace an existing metadata database only after taking a fresh copy of the current file:

```powershell
.\.venv\Scripts\python.exe scripts\restore_metadata.py --database data\freemail.sqlite --input .freemail-qa\backups\metadata.json --force
```

## Mail Store

The metadata backup does not include admin bearer sessions, mailbox browser sessions, outbound rate counters, push-device registrations, encrypted push-provider tokens, push-notification delivery records, mailbox messages, attachments, indexes, or queues. Messages, attachments, indexes, and queues live in the Compose-managed Stalwart Docker volume mounted at `/var/lib/stalwart` during the current Stalwart spike. With the default Compose project name in this repo, Docker names that volume `freemail_freemail_stalwart`.

For local recovery drills, stop writers before archiving or replacing the volume. At minimum, stop the Stalwart container before taking the archive:

```powershell
docker inspect freemail-mail-core-1 --format '{{json .Mounts}}'
docker compose --profile mail-core stop mail-core
.\.venv\Scripts\python.exe scripts\backup_mail_store.py --volume freemail_freemail_stalwart --output .freemail-qa\backups\stalwart-mail-store.tar.gz
docker compose --profile mail-core up -d mail-core
```

Restore into a separate drill volume first:

```powershell
.\.venv\Scripts\python.exe scripts\restore_mail_store.py --volume freemail_stalwart_restore --input .freemail-qa\backups\stalwart-mail-store.tar.gz --force
```

To replace the active Stalwart volume, stop all writers, take a fresh backup of the current active volume, and then restore with `--force`:

```powershell
docker compose --profile mail-core stop mail-core
.\.venv\Scripts\python.exe scripts\backup_mail_store.py --volume freemail_freemail_stalwart --output .freemail-qa\backups\stalwart-mail-store-before-restore.tar.gz
.\.venv\Scripts\python.exe scripts\restore_mail_store.py --volume freemail_freemail_stalwart --input .freemail-qa\backups\stalwart-mail-store.tar.gz --force
docker compose --profile mail-core up -d mail-core
```

After any restore drill, validate the restored stack with:

```powershell
.\.venv\Scripts\python.exe scripts\qa_mail_core.py --strict
.\.venv\Scripts\python.exe scripts\qa_mail_flow.py --email admin@example.com --secrets-json secrets\mail-core-users.json --inbound-recipient hello@example.com
```

## Release Gate

Before private beta, record evidence that:

- Metadata export completes and the JSON is stored outside the repository.
- `scripts\collect_restore_drill_evidence.py` proves metadata restore into a new database, Stalwart apply-plan export from restored metadata, and mail-store archive restore into a drill Docker volume.
- Active-volume restore is tested only when all writers are stopped and a fresh rollback archive exists.
- DKIM records generated from restored key material match the active DNS guidance.
- Release and private-beta gate outputs record SHA-256 checksums for the metadata backup, mail-store backup, and restore-drill evidence files. Private-beta gate output also records checksums for mail-flow, queue, deliverability/abuse, and acceptance evidence files.
