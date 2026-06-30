from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import sqlite3
from typing import Any


BACKUP_SCHEMA_VERSION = 1
BACKUP_TABLES = (
    "domains",
    "users",
    "mailboxes",
    "aliases",
    "dkim_keys",
    "audit_log",
    "mailbox_preferences",
    "mailbox_contacts",
)
RESTORE_DELETE_ORDER = tuple(reversed(BACKUP_TABLES))


class BackupError(ValueError):
    pass


def export_metadata_backup(
    connection: sqlite3.Connection,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": BACKUP_SCHEMA_VERSION,
        "generatedAt": generated_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "tables": {table: _export_table(connection, table) for table in BACKUP_TABLES},
        "excludedTables": [
            "admin_sessions",
            "mailbox_sessions",
            "outbound_send_events",
            "mailbox_push_devices",
            "mailbox_push_notifications",
        ],
    }


def restore_metadata_backup(
    connection: sqlite3.Connection,
    payload: Mapping[str, Any],
    *,
    force: bool = False,
) -> None:
    tables = _validated_tables(payload)
    if not force and _has_existing_metadata(connection):
        raise BackupError("metadata database is not empty; pass force=True to replace existing metadata")

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            if force:
                for table in RESTORE_DELETE_ORDER:
                    connection.execute(f"DELETE FROM {table}")
            for table in BACKUP_TABLES:
                _restore_table(connection, table, tables[table])
    except sqlite3.IntegrityError as error:
        raise BackupError(str(error)) from error


def _export_table(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    order_column = _order_column(table)
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY {order_column}").fetchall()
    return [dict(row) for row in rows]


def _order_column(table: str) -> str:
    if table == "mailbox_contacts":
        return "mailbox_email, contact_email"
    if table == "mailbox_preferences":
        return "mailbox_email"
    return "id"


def _validated_tables(payload: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if payload.get("schemaVersion") != BACKUP_SCHEMA_VERSION:
        raise BackupError(f"unsupported backup schema version: {payload.get('schemaVersion')}")
    raw_tables = payload.get("tables")
    if not isinstance(raw_tables, Mapping):
        raise BackupError("backup payload must contain a tables object")

    tables: dict[str, list[dict[str, Any]]] = {}
    for table in BACKUP_TABLES:
        raw_rows = raw_tables.get(table)
        if raw_rows is None and table == "mailbox_contacts":
            raw_rows = []
        if not isinstance(raw_rows, list):
            raise BackupError(f"backup payload must contain a {table} row list")
        tables[table] = [_validated_row(table, row) for row in raw_rows]
    return tables


def _validated_row(table: str, row: object) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise BackupError(f"{table} backup rows must be objects")
    return dict(row)


def _has_existing_metadata(connection: sqlite3.Connection) -> bool:
    for table in BACKUP_TABLES:
        row = connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
        if row is not None:
            return True
    return False


def _restore_table(connection: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    allowed_columns = _table_columns(connection, table)
    for row in rows:
        columns = list(row.keys())
        unexpected_columns = sorted(set(columns) - allowed_columns)
        if unexpected_columns:
            raise BackupError(f"{table} contains unsupported columns: {', '.join(unexpected_columns)}")
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        values = [row[column] for column in columns]
        connection.execute(f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})", values)


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows}
