import json
import sqlite3
import subprocess
import sys

import pytest

from freemail_api import database
from freemail_api.backup import BackupError, export_metadata_backup, restore_metadata_backup
from freemail_api.schemas import (
    AliasCreate,
    DkimKeyCreate,
    DomainCreate,
    MailboxCreate,
    StoredUserCreate,
    StoredUserInvitationCreate,
)


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
            encrypted_push_token="encrypted-push-token",
            provider="contract-only",
        )
        database.create_mailbox_push_notifications(
            connection,
            email="admin@example.com",
            title="FreeMail",
            body="New message",
        )
        database.upsert_mailbox_preferences(
            connection,
            email="admin@example.com",
            display_name="Admin User",
            signature="Regards,\nAdmin",
        )
        database.upsert_admin_totp_secret(
            connection,
            user_id=1,
            encrypted_secret="encrypted-totp-secret",
            actor="test",
        )
        database.create_user_invitation(
            connection,
            StoredUserInvitationCreate(
                email="pending@example.com",
                display_name="Pending User",
                token_hash="a" * 64,
                expires_at=2_000_000_000,
            ),
            actor="test",
        )
        database.enable_admin_totp(connection, user_id=1, actor="test")
        database.upsert_saved_mailbox_contact(
            connection,
            email="admin@example.com",
            contact_email="saved@example.net",
            display_name="Saved Contact",
            notes="Release contact",
        )
        database.upsert_mailbox_sender_rule(
            connection,
            email="admin@example.com",
            sender_email="blocked@example.net",
            action="block",
            notes="Abuse report",
        )
        database.upsert_mailbox_recipient_rule(
            connection,
            email="admin@example.com",
            recipient_email="blocked-recipient@example.net",
            action="block",
            notes="Outbound abuse report",
        )
        backup = export_metadata_backup(connection, generated_at="2026-06-30T00:00:00+00:00")

    assert backup["schemaVersion"] == 1
    assert backup["excludedTables"] == [
        "admin_sessions",
        "mailbox_sessions",
        "outbound_send_events",
        "mailbox_push_devices",
        "mailbox_push_notifications",
    ]
    assert "admin_sessions" not in backup["tables"]
    assert "mailbox_sessions" not in backup["tables"]
    assert "mailbox_push_devices" not in backup["tables"]
    assert "mailbox_push_notifications" not in backup["tables"]
    assert backup["tables"]["dkim_keys"][0]["private_key_pem"] == "private-key-pem"
    assert backup["tables"]["admin_totp_secrets"][0]["encrypted_secret"] == "encrypted-totp-secret"
    assert backup["tables"]["admin_totp_secrets"][0]["enabled"] == 1
    assert backup["tables"]["user_invitations"][0]["email"] == "pending@example.com"
    assert backup["tables"]["user_invitations"][0]["token_hash"] == "a" * 64
    assert backup["tables"]["mailboxes"][0]["quota_bytes"] == 10_737_418_240
    assert backup["tables"]["mailbox_preferences"][0]["signature"] == "Regards,\nAdmin"
    assert backup["tables"]["mailbox_contacts"][0]["contact_email"] == "saved@example.net"
    assert backup["tables"]["mailbox_sender_rules"][0]["sender_email"] == "blocked@example.net"
    assert backup["tables"]["mailbox_sender_rules"][0]["action"] == "block"
    assert backup["tables"]["mailbox_recipient_rules"][0]["recipient_email"] == "blocked-recipient@example.net"
    assert backup["tables"]["mailbox_recipient_rules"][0]["action"] == "block"

    with database.connect(str(target_path)) as connection:
        restore_metadata_backup(connection, backup)

    with database.connect(str(target_path)) as connection:
        assert [dict(row) for row in database.list_rows(connection, "domains")] == backup["tables"]["domains"]
        assert [dict(row) for row in database.list_rows(connection, "users")] == backup["tables"]["users"]
        assert [dict(row) for row in database.list_rows(connection, "user_invitations")] == backup["tables"][
            "user_invitations"
        ]
        assert [dict(row) for row in database.list_rows(connection, "mailboxes")] == backup["tables"]["mailboxes"]
        assert [dict(row) for row in database.list_rows(connection, "aliases")] == backup["tables"]["aliases"]
        assert [dict(row) for row in database.list_rows(connection, "dkim_keys")] == backup["tables"]["dkim_keys"]
        assert [dict(row) for row in database.list_rows(connection, "audit_log")] == backup["tables"]["audit_log"]
        assert [dict(row) for row in database.list_rows(connection, "admin_totp_secrets")] == backup["tables"][
            "admin_totp_secrets"
        ]
        assert [dict(row) for row in database.list_rows(connection, "mailbox_preferences")] == backup["tables"][
            "mailbox_preferences"
        ]
        assert [dict(row) for row in database.list_rows(connection, "mailbox_contacts")] == backup["tables"][
            "mailbox_contacts"
        ]
        assert [dict(row) for row in database.list_rows(connection, "mailbox_sender_rules")] == backup["tables"][
            "mailbox_sender_rules"
        ]
        assert [dict(row) for row in database.list_rows(connection, "mailbox_recipient_rules")] == backup["tables"][
            "mailbox_recipient_rules"
        ]
        assert connection.execute("SELECT COUNT(*) FROM admin_sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM mailbox_sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM outbound_send_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM mailbox_push_devices").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM mailbox_push_notifications").fetchone()[0] == 0


def test_initialize_migrates_existing_push_tables_for_encrypted_tokens(tmp_path):
    database_path = tmp_path / "existing.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE mailbox_push_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mailbox_email TEXT NOT NULL,
                device_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                push_token_hash TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'contract-only',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(mailbox_email, device_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE mailbox_push_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mailbox_email TEXT NOT NULL,
                device_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                provider_message_id TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                delivered_at TEXT
            )
            """
        )

    database.initialize(str(database_path))

    with database.connect(str(database_path)) as connection:
        device_columns = {row["name"] for row in connection.execute("PRAGMA table_info(mailbox_push_devices)")}
        notification_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(mailbox_push_notifications)")
        }
    assert "encrypted_push_token" in device_columns
    assert "encrypted_push_token" in notification_columns


def test_initialize_migrates_existing_mailboxes_for_quota_bytes(tmp_path):
    database_path = tmp_path / "existing.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                admin_role TEXT NOT NULL DEFAULT 'member',
                status TEXT NOT NULL DEFAULT 'invited',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE mailboxes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                local_part TEXT NOT NULL,
                domain_id INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
                address TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(local_part, domain_id)
            );
            """
        )

    database.initialize(str(database_path))

    with database.connect(str(database_path)) as connection:
        mailbox_columns = {row["name"] for row in connection.execute("PRAGMA table_info(mailboxes)")}

    assert "quota_bytes" in mailbox_columns


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


def test_metadata_restore_accepts_schema_one_backup_without_saved_contacts(tmp_path):
    source_path = tmp_path / "source.sqlite"
    target_path = tmp_path / "target.sqlite"
    database.initialize(str(source_path))
    database.initialize(str(target_path))

    with database.connect(str(source_path)) as connection:
        _seed_metadata(connection)
        backup = export_metadata_backup(connection)

    del backup["tables"]["mailbox_contacts"]

    with database.connect(str(target_path)) as connection:
        restore_metadata_backup(connection, backup)
        contacts = database.list_rows(connection, "mailbox_contacts")

    assert contacts == []


def test_metadata_restore_accepts_schema_one_backup_without_user_invitations(tmp_path):
    source_path = tmp_path / "source.sqlite"
    target_path = tmp_path / "target.sqlite"
    database.initialize(str(source_path))
    database.initialize(str(target_path))

    with database.connect(str(source_path)) as connection:
        _seed_metadata(connection)
        backup = export_metadata_backup(connection)

    del backup["tables"]["user_invitations"]

    with database.connect(str(target_path)) as connection:
        restore_metadata_backup(connection, backup)
        invitations = database.list_rows(connection, "user_invitations")

    assert invitations == []


def test_metadata_restore_accepts_schema_one_backup_without_sender_rules(tmp_path):
    source_path = tmp_path / "source.sqlite"
    target_path = tmp_path / "target.sqlite"
    database.initialize(str(source_path))
    database.initialize(str(target_path))

    with database.connect(str(source_path)) as connection:
        _seed_metadata(connection)
        backup = export_metadata_backup(connection)

    del backup["tables"]["mailbox_sender_rules"]

    with database.connect(str(target_path)) as connection:
        restore_metadata_backup(connection, backup)
        rules = database.list_rows(connection, "mailbox_sender_rules")

    assert rules == []


def test_metadata_restore_accepts_schema_one_backup_without_recipient_rules(tmp_path):
    source_path = tmp_path / "source.sqlite"
    target_path = tmp_path / "target.sqlite"
    database.initialize(str(source_path))
    database.initialize(str(target_path))

    with database.connect(str(source_path)) as connection:
        _seed_metadata(connection)
        backup = export_metadata_backup(connection)

    del backup["tables"]["mailbox_recipient_rules"]

    with database.connect(str(target_path)) as connection:
        restore_metadata_backup(connection, backup)
        rules = database.list_rows(connection, "mailbox_recipient_rules")

    assert rules == []


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
        StoredUserCreate(
            email="admin@example.com",
            displayName="Admin User",
            passwordHash="argon2id-placeholder-hash",
            isAdmin=True,
        ),
        "test",
    )
    database.create_mailbox(
        connection,
        MailboxCreate(
            userId=int(user["id"]),
            localPart="admin",
            domainId=int(domain["id"]),
            quotaBytes=10_737_418_240,
        ),
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
