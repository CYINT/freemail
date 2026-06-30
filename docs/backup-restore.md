# Backup And Restore

FreeMail currently has two persistence surfaces:

- API metadata in SQLite at `FREEMAIL_DB_PATH`.
- Mail-core data in the Docker volume mounted at `/var/lib/stalwart`.

The metadata backup tools cover domains, users, mailboxes, aliases, DKIM keys, and audit logs. They intentionally exclude browser mailbox sessions, outbound rate-limit counters, push-device registrations, and push-notification delivery records.

Metadata backups include DKIM private keys and password hashes. Treat every backup file as sensitive operational material: encrypt it at rest, keep it out of Git, and restrict access to administrators.

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

The metadata backup does not include mailbox browser sessions, outbound rate counters, push-device registrations, push-notification delivery records, mailbox messages, attachments, indexes, or queues. Messages, attachments, indexes, and queues live in the Compose-managed Stalwart Docker volume mounted at `/var/lib/stalwart` during the current Stalwart spike. With the default Compose project name in this repo, Docker names that volume `freemail_freemail_stalwart`.

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
- Metadata restore succeeds into a new database.
- The restored metadata can export a Stalwart apply plan.
- Mail-core volume backup and restore are tested in the target deployment environment, first into a drill volume and then against the active volume only when a rollback archive exists.
- DKIM records generated from restored key material match the active DNS guidance.
