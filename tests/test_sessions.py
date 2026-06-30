import pytest

from freemail_api import database
from freemail_api.sessions import bearer_token
from freemail_api.sessions import create_mailbox_session
from freemail_api.sessions import InvalidSessionError
from freemail_api.sessions import resolve_mailbox_session
from freemail_api.sessions import revoke_mailbox_session
from freemail_api.sessions import SessionConfigurationError


def test_mailbox_session_encrypts_and_resolves_password(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    database.initialize(str(db_path))
    with database.connect(str(db_path)) as connection:
        created = create_mailbox_session(
            connection,
            email="Admin@Example.com",
            password="secret",
            secret="test-session-secret",
            ttl_seconds=600,
            now=1000,
        )
        row = database.get_mailbox_session(connection, token_hash=_hash(created.token), now=1000)
        assert row["email"] == "admin@example.com"
        assert row["encrypted_password"] != "secret"

        credentials = resolve_mailbox_session(
            connection,
            token=created.token,
            secret="test-session-secret",
            now=1000,
        )

    assert credentials.email == "admin@example.com"
    assert credentials.password == "secret"


def test_mailbox_session_rejects_missing_secret(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    database.initialize(str(db_path))
    with database.connect(str(db_path)) as connection:
        with pytest.raises(SessionConfigurationError):
            create_mailbox_session(
                connection,
                email="admin@example.com",
                password="secret",
                secret=None,
                ttl_seconds=600,
            )


def test_mailbox_session_expires_and_revokes(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    database.initialize(str(db_path))
    with database.connect(str(db_path)) as connection:
        created = create_mailbox_session(
            connection,
            email="admin@example.com",
            password="secret",
            secret="test-session-secret",
            ttl_seconds=600,
            now=1000,
        )

        with pytest.raises(InvalidSessionError):
            resolve_mailbox_session(connection, token=created.token, secret="test-session-secret", now=2000)

        created = create_mailbox_session(
            connection,
            email="admin@example.com",
            password="secret",
            secret="test-session-secret",
            ttl_seconds=600,
            now=3000,
        )
        revoke_mailbox_session(connection, created.token)

        with pytest.raises(InvalidSessionError):
            resolve_mailbox_session(connection, token=created.token, secret="test-session-secret", now=3000)


def test_bearer_token_parses_authorization_header():
    assert bearer_token("Bearer abc") == "abc"
    assert bearer_token("Basic abc") is None
    assert bearer_token(None) is None


def _hash(token: str) -> str:
    from freemail_api.sessions import hash_session_token

    return hash_session_token(token)
