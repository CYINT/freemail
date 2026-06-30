import json

import pytest

from scripts import qa_mailbox_preferences_api


def test_probe_preferences_updates_verifies_and_restores(monkeypatch):
    state = {"displayName": "Existing", "signature": "Original"}
    calls = []

    def fake_json_request(base_url, path, email, password, *, method="GET", payload=None):
        calls.append((path, method, payload))
        assert base_url == "http://api"
        assert email == "admin@example.com"
        assert password == "secret"
        if method == "PUT":
            state.update(payload)
        return {"mailboxEmail": "admin@example.com", **state}

    monkeypatch.setattr(qa_mailbox_preferences_api, "_json_request", fake_json_request)

    result = qa_mailbox_preferences_api._probe_preferences("http://api", "admin@example.com", "secret")

    assert result["updated"] is True
    assert result["restored"] is True
    assert state == {"displayName": "Existing", "signature": "Original"}
    assert [call[1] for call in calls] == ["GET", "PUT", "GET", "PUT"]


def test_load_password_reads_utf8_sig_secret_file(tmp_path):
    path = tmp_path / "secrets.json"
    path.write_text(json.dumps({"admin@example.com": "secret"}), encoding="utf-8-sig")

    assert qa_mailbox_preferences_api._load_password(str(path), "Admin@Example.com") == "secret"


def test_load_password_requires_known_email(tmp_path):
    path = tmp_path / "secrets.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing password"):
        qa_mailbox_preferences_api._load_password(str(path), "admin@example.com")
