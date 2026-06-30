# Backup And Restore

FreeMail currently has two persistence surfaces:

- API metadata in SQLite at `FREEMAIL_DB_PATH`.
- Mail-core data in the Docker volume mounted at `/var/lib/stalwart`.

The metadata backup tools cover domains, users, mailboxes, aliases, DKIM keys, and audit logs. They intentionally exclude browser mailbox sessions and outbound rate-limit counters.

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

The metadata backup does not include mailbox messages, attachments, indexes, or queues. Those live in the `freemail_stalwart` Docker volume during the current Stalwart spike.

For local recovery drills, stop writers before copying the volume contents, then validate the restored stack with:

```powershell
docker compose --profile mail-core up -d mail-core
.\.venv\Scripts\python.exe scripts\qa_mail_core.py --strict
.\.venv\Scripts\python.exe scripts\qa_mail_flow.py --email admin@example.com --secrets-json secrets\mail-core-users.json --inbound-recipient hello@example.com
```

## Release Gate

Before private beta, record evidence that:

- Metadata export completes and the JSON is stored outside the repository.
- Metadata restore succeeds into a new database.
- The restored metadata can export a Stalwart apply plan.
- Mail-core volume backup and restore are tested in the target deployment environment.
- DKIM records generated from restored key material match the active DNS guidance.
