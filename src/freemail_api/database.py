from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .schemas import AliasCreate, BootstrapAdminCreate, DkimKeyCreate, DomainCreate, MailboxCreate, UserCreate


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'invited',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mailboxes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    local_part TEXT NOT NULL,
    domain_id INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    address TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(local_part, domain_id)
);

CREATE TABLE IF NOT EXISTS aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL UNIQUE,
    destination TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dkim_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    selector TEXT NOT NULL,
    dns_name TEXT NOT NULL,
    public_txt TEXT NOT NULL,
    private_key_pem TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain_id, selector)
);

CREATE TABLE IF NOT EXISTS mailbox_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    encrypted_password TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mailbox_sessions_expires_at ON mailbox_sessions(expires_at);
"""


class DuplicateRecordError(ValueError):
    pass


class MissingRecordError(ValueError):
    pass


def connect(database_path: str) -> sqlite3.Connection:
    path = Path(database_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(database_path: str) -> None:
    with connect(database_path) as connection:
        connection.executescript(SCHEMA)


def list_rows(connection: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    allowed_tables = {"domains", "users", "mailboxes", "aliases", "audit_log", "dkim_keys"}
    if table not in allowed_tables:
        raise ValueError(f"Unsupported table: {table}")
    return list(connection.execute(f"SELECT * FROM {table} ORDER BY id"))


def has_admin_user(connection: sqlite3.Connection) -> bool:
    row = connection.execute("SELECT 1 FROM users WHERE is_admin = 1 LIMIT 1").fetchone()
    return row is not None


def bootstrap_admin(connection: sqlite3.Connection, payload: BootstrapAdminCreate, actor: str) -> dict[str, sqlite3.Row]:
    if has_admin_user(connection):
        raise DuplicateRecordError("administrator already exists")
    domain = create_domain(connection, DomainCreate(name=payload.domain_name), actor)
    user = create_user(
        connection,
        UserCreate(
            email=payload.email,
            display_name=payload.display_name,
            password_hash=payload.password_hash,
            is_admin=True,
        ),
        actor,
    )
    mailbox = create_mailbox(
        connection,
        MailboxCreate(
            user_id=int(user["id"]),
            local_part=payload.mailbox_local_part,
            domain_id=int(domain["id"]),
        ),
        actor,
    )
    return {"domain": domain, "user": user, "mailbox": mailbox}


def create_domain(connection: sqlite3.Connection, payload: DomainCreate, actor: str) -> sqlite3.Row:
    domain_name = payload.name.lower().strip(".")
    row_id = _execute_insert(connection, "INSERT INTO domains (name) VALUES (?)", [domain_name])
    _audit(connection, actor, "domain.create", "domain", row_id)
    connection.commit()
    return _get_row(connection, "domains", row_id)


def create_user(connection: sqlite3.Connection, payload: UserCreate, actor: str) -> sqlite3.Row:
    row_id = _execute_insert(
        connection,
        """
        INSERT INTO users (email, display_name, password_hash, is_admin)
        VALUES (?, ?, ?, ?)
        """,
        [payload.email.lower(), payload.display_name, payload.password_hash, int(payload.is_admin)],
    )
    _audit(connection, actor, "user.invite", "user", row_id)
    connection.commit()
    return _get_row(connection, "users", row_id)


def create_mailbox(connection: sqlite3.Connection, payload: MailboxCreate, actor: str) -> sqlite3.Row:
    domain = _get_row(connection, "domains", payload.domain_id)
    _get_row(connection, "users", payload.user_id)
    address = f"{payload.local_part.lower()}@{domain['name']}"
    row_id = _execute_insert(
        connection,
        """
        INSERT INTO mailboxes (user_id, local_part, domain_id, address)
        VALUES (?, ?, ?, ?)
        """,
        [payload.user_id, payload.local_part.lower(), payload.domain_id, address],
    )
    _audit(connection, actor, "mailbox.create", "mailbox", row_id)
    connection.commit()
    return _get_row(connection, "mailboxes", row_id)


def create_alias(connection: sqlite3.Connection, payload: AliasCreate, actor: str) -> sqlite3.Row:
    row_id = _execute_insert(
        connection,
        "INSERT INTO aliases (source, destination) VALUES (?, ?)",
        [payload.source.lower(), payload.destination.lower()],
    )
    _audit(connection, actor, "alias.create", "alias", row_id)
    connection.commit()
    return _get_row(connection, "aliases", row_id)


def create_dkim_key(
    connection: sqlite3.Connection,
    payload: DkimKeyCreate,
    public_txt: str,
    private_key_pem: str,
    actor: str,
) -> sqlite3.Row:
    domain = _get_row(connection, "domains", payload.domain_id)
    selector = payload.selector.lower()
    dns_name = f"{selector}._domainkey.{domain['name']}"
    row_id = _execute_insert(
        connection,
        """
        INSERT INTO dkim_keys (domain_id, selector, dns_name, public_txt, private_key_pem)
        VALUES (?, ?, ?, ?, ?)
        """,
        [payload.domain_id, selector, dns_name, public_txt, private_key_pem],
    )
    _audit(connection, actor, "dkim.create", "dkim_key", row_id)
    connection.commit()
    return _get_row(connection, "dkim_keys", row_id)


def get_domain(connection: sqlite3.Connection, domain_id: int) -> sqlite3.Row:
    return _get_row(connection, "domains", domain_id)


def list_dkim_keys_for_domain(connection: sqlite3.Connection, domain_id: int) -> list[sqlite3.Row]:
    _get_row(connection, "domains", domain_id)
    return list(connection.execute("SELECT * FROM dkim_keys WHERE domain_id = ? ORDER BY id", [domain_id]))


def create_mailbox_session(
    connection: sqlite3.Connection,
    *,
    token_hash: str,
    email: str,
    encrypted_password: str,
    expires_at: int,
) -> sqlite3.Row:
    row_id = _execute_insert(
        connection,
        """
        INSERT INTO mailbox_sessions (token_hash, email, encrypted_password, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        [token_hash, email.lower(), encrypted_password, expires_at],
    )
    connection.commit()
    return _get_row(connection, "mailbox_sessions", row_id)


def get_mailbox_session(connection: sqlite3.Connection, token_hash: str, now: int) -> sqlite3.Row | None:
    delete_expired_mailbox_sessions(connection, now)
    row = connection.execute(
        """
        SELECT * FROM mailbox_sessions
        WHERE token_hash = ? AND expires_at > ?
        """,
        [token_hash, now],
    ).fetchone()
    return row


def revoke_mailbox_session(connection: sqlite3.Connection, token_hash: str) -> None:
    connection.execute("DELETE FROM mailbox_sessions WHERE token_hash = ?", [token_hash])
    connection.commit()


def delete_expired_mailbox_sessions(connection: sqlite3.Connection, now: int) -> None:
    connection.execute("DELETE FROM mailbox_sessions WHERE expires_at <= ?", [now])
    connection.commit()


def _execute_insert(connection: sqlite3.Connection, statement: str, values: Iterable[object]) -> int:
    try:
        cursor = connection.execute(statement, list(values))
    except sqlite3.IntegrityError as error:
        message = str(error)
        if "FOREIGN KEY" in message:
            raise MissingRecordError(message) from error
        raise DuplicateRecordError(message) from error
    return int(cursor.lastrowid)


def _audit(connection: sqlite3.Connection, actor: str, action: str, target_type: str, target_id: int) -> None:
    connection.execute(
        """
        INSERT INTO audit_log (actor, action, target_type, target_id)
        VALUES (?, ?, ?, ?)
        """,
        [actor, action, target_type, target_id],
    )


def _get_row(connection: sqlite3.Connection, table: str, row_id: int) -> sqlite3.Row:
    row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", [row_id]).fetchone()
    if row is None:
        raise MissingRecordError(f"{table} id {row_id} was not found")
    return row
