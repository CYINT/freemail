import json

import pytest

from scripts.qa_mailbox_import_api import _load_password
from scripts.qa_mailbox_import_api import _message_source


def test_load_password_reads_lowercase_email(tmp_path):
    secrets = tmp_path / "secrets.json"
    secrets.write_text(json.dumps({"admin@example.com": "secret"}), encoding="utf-8")

    assert _load_password(str(secrets), "ADMIN@example.com") == "secret"


def test_load_password_requires_secret_entry(tmp_path):
    secrets = tmp_path / "secrets.json"
    secrets.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        _load_password(str(secrets), "admin@example.com")


def test_message_source_builds_rfc822_headers():
    source = _message_source(sender="admin@example.com", recipient="admin@example.com", subject="Import")

    assert b"Subject: Import" in source
    assert b"Message-ID:" in source
