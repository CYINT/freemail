import json

import pytest

from scripts.qa_mailbox_move_api import _load_password


def test_load_password_reads_lowercase_email(tmp_path):
    path = tmp_path / "secrets.json"
    path.write_text(json.dumps({"admin@example.com": "secret"}), encoding="utf-8")

    assert _load_password(str(path), "ADMIN@example.com") == "secret"


def test_load_password_requires_secret_entry(tmp_path):
    path = tmp_path / "secrets.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing password"):
        _load_password(str(path), "admin@example.com")
