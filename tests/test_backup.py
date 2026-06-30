import json
import sqlite3
import subprocess
import sys

import pytest

from freemail_api import database
from freemail_api.backup import BackupError, export_metadata_backup, restore_metadata_backup
from freemail_api.schemas import AliasCreate, DkimKeyCreate, DomainCreate, MailboxCreate, UserCreate


def test_metadata_backup_round_trip_preserves_core_metadata_and_key_material(tmp_path):
    source_path = tmp_path / "source.sqlite"
    target_path = tmp_path / "target.sqlite"
    database.initialize(str(source_path))
    database.initialize(str(target_path))

    with database.connect(str(source_path)) as connection:
        _seed_metadata(connection)
        database.create_mailbox_session(
            connection,
            token_hash="session-token-hash",
            email="admin@example.com",
            encrypted_password="encrypted-session-password",
            expires_at=2_000_000_000,
        )
        database.record_outbound_send_event(
            connection,
            email="admin@example.com",
            recipient_count=1,
            created_at=1_700_000_000,
        )
        database.upsert_mailbox_push_device(
            connection,
            email="admin@example.com",
            device_id="device-123",
            platform="development",
            push_token_hash="hashed-push-token",
            provider="contract-only",
        )
        backup = export_metadata_backup(connection, generated_at="2026-06-30T00:00:00+00:00")

    assert backup["schemaVersion"] == 1
    assert backup["excludedTables"] == ["mailbox_sessions", "outbound_send_events", "mailbox_push_devices"]
    assert "mailbox_sessions" not in backup["tables"]
    assert "mailbox_push_devices" not in backup["tables"]
    assert backup["tables"]["dkim_keys"][0]["private_key_pem"] == "private-key-pem"

    with database.connect(str(target_path)) as connection:
        restore_metadata_backup(connection, backup)

    with database.connect(str(target_path)) as connection:
        assert [dict(row) for row in database.list_rows(connection, "domains")] == backup["tables"]["domains"]
        assert [dict(row) for row in database.list_rows(connection, "users")] == backup["tables"]["users"]
        assert [dict(row) for row in database.list_rows(connection, "mailboxes")] == backup["tables"]["mailboxes"]
        assert [dict(row) for row in database.list_rows(connection, "aliases")] == backup["tables"]["aliases"]
        assert [dict(row) for row in database.list_rows(connection, "dkim_keys")] == backup["tables"]["dkim_keys"]
        assert [dict(row) for row in database.list_rows(connection, "audit_log")] == backup["tables"]["audit_log"]
        assert connection.execute("SELECT COUNT(*) FROM mailbox_sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM outbound_send_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM mailbox_push_devices").fetchone()[0] == 0


def test_metadata_restore_refuses_non_empty_database_without_force(tmp_path):
    source_path = tmp_path / "source.sqlite"
    target_path = tmp_path / "target.sqlite"
    database.initialize(str(source_path))
    database.initialize(str(target_path))

    with database.connect(str(source_path)) as connection:
        _seed_metadata(connection)
        backup = export_metadata_backup(connection)

    with database.connect(str(target_path)) as connection:
        database.create_domain(connection, DomainCreate(name="existing.example"), "test")
        with pytest.raises(BackupError, match="not empty"):
            restore_metadata_backup(connection, backup)

        restore_metadata_backup(connection, backup, force=True)
        domains = database.list_rows(connection, "domains")

    assert [domain["name"] for domain in domains] == ["example.com"]


def test_metadata_restore_validates_schema_version(tmp_path):
    path = tmp_path / "freemail.sqlite"
    database.initialize(str(path))

    with database.connect(str(path)) as connection:
        with pytest.raises(BackupError, match="unsupported backup schema version"):
            restore_metadata_backup(connection, {"schemaVersion": 999, "tables": {}})


def test_metadata_backup_and_restore_scripts_round_trip(tmp_path):
    source_path = tmp_path / "source.sqlite"
    target_path = tmp_path / "target.sqlite"
    backup_path = tmp_path / "backups" / "metadata.json"
    database.initialize(str(source_path))

    with database.connect(str(source_path)) as connection:
        _seed_metadata(connection)

    export_result = subprocess.run(
        [
            sys.executable,
            "scripts/backup_metadata.py",
            "--database",
            str(source_path),
            "--output",
            str(backup_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert export_result.returncode == 0, export_result.stderr
    assert json.loads(backup_path.read_text(encoding="utf-8"))["schemaVersion"] == 1

    restore_result = subprocess.run(
        [
            sys.executable,
            "scripts/restore_metadata.py",
            "--database",
            str(target_path),
            "--input",
            str(backup_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert restore_result.returncode == 0, restore_result.stderr

    with sqlite3.connect(target_path) as connection:
        connection.row_factory = sqlite3.Row
        assert connection.execute("SELECT name FROM domains").fetchone()["name"] == "example.com"


def test_metadata_backup_script_initializes_missing_schema(tmp_path):
    source_path = tmp_path / "source.sqlite"
    backup_path = tmp_path / "metadata.json"

    export_result = subprocess.run(
        [
            sys.executable,
            "scripts/backup_metadata.py",
            "--database",
            str(source_path),
            "--output",
            str(backup_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert export_result.returncode == 0, export_result.stderr
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 1
    assert payload["tables"]["dkim_keys"] == []


def _seed_metadata(connection: sqlite3.Connection) -> None:
    domain = database.create_domain(connection, DomainCreate(name="example.com"), "test")
    user = database.create_user(
        connection,
        UserCreate(
            email="admin@example.com",
            displayName="Admin User",
            passwordHash="argon2id-placeholder-hash",
            isAdmin=True,
        ),
        "test",
    )
    database.create_mailbox(
        connection,
        MailboxCreate(userId=int(user["id"]), localPart="admin", domainId=int(domain["id"])),
        "test",
    )
    database.create_alias(
        connection,
        AliasCreate(source="hello@example.com", destination="admin@example.com"),
        "test",
    )
    database.create_dkim_key(
        connection,
        DkimKeyCreate(domainId=int(domain["id"]), selector="mail"),
        "v=DKIM1; k=rsa; p=public",
        "private-key-pem",
        "test",
    )
