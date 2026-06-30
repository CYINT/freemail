from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import secrets
import sqlite3
import time

from . import database
from .secret_box import decrypt_text
from .secret_box import encrypt_text
from .secret_box import SecretBoxConfigurationError
from .secret_box import SecretBoxDecryptionError


@dataclass(frozen=True)
class MailboxCredentials:
    email: str
    password: str


@dataclass(frozen=True)
class CreatedMailboxSession:
    token: str
    email: str
    expires_at: int


class SessionConfigurationError(RuntimeError):
    pass


class InvalidSessionError(ValueError):
    pass


def create_mailbox_session(
    connection: sqlite3.Connection,
    *,
    email: str,
    password: str,
    secret: str | None,
    ttl_seconds: int,
    now: int | None = None,
) -> CreatedMailboxSession:
    active_now = int(time.time()) if now is None else now
    token = secrets.token_urlsafe(32)
    expires_at = active_now + max(300, ttl_seconds)
    try:
        encrypted_password = encrypt_text(password, secret)
    except SecretBoxConfigurationError as error:
        raise SessionConfigurationError("FREEMAIL_SESSION_SECRET is not configured") from error
    database.create_mailbox_session(
        connection,
        token_hash=hash_session_token(token),
        email=email,
        encrypted_password=encrypted_password,
        expires_at=expires_at,
    )
    return CreatedMailboxSession(token=token, email=email.lower(), expires_at=expires_at)


def resolve_mailbox_session(
    connection: sqlite3.Connection,
    *,
    token: str,
    secret: str | None,
    now: int | None = None,
) -> MailboxCredentials:
    active_now = int(time.time()) if now is None else now
    row = database.get_mailbox_session(connection, hash_session_token(token), active_now)
    if row is None:
        raise InvalidSessionError("Mailbox session not found")
    try:
        password = decrypt_text(str(row["encrypted_password"]), secret)
    except SecretBoxConfigurationError as error:
        raise SessionConfigurationError("FREEMAIL_SESSION_SECRET is not configured") from error
    except SecretBoxDecryptionError as error:
        raise InvalidSessionError("Mailbox session could not be decrypted") from error
    return MailboxCredentials(email=str(row["email"]), password=password)


def revoke_mailbox_session(connection: sqlite3.Connection, token: str) -> None:
    database.revoke_mailbox_session(connection, hash_session_token(token))


def hash_session_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _separator, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()
