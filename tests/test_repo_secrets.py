from pathlib import Path

from scripts import qa_repo_secrets


def test_repo_secret_scan_rejects_tracked_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FREEMAIL_ADMIN_API_TOKEN=real-token\n", encoding="utf-8")
    monkeypatch.setattr(qa_repo_secrets, "_tracked_files", lambda _root: [Path(".env")])

    failures = qa_repo_secrets.scan_repo(tmp_path)

    assert "forbidden tracked secret/signing file: .env" in failures


def test_repo_secret_scan_rejects_private_key_outside_fixtures(tmp_path, monkeypatch):
    source = tmp_path / "src" / "secret.py"
    source.parent.mkdir()
    source.write_text("KEY = '-----BEGIN PRIVATE KEY-----\\nsecret\\n-----END PRIVATE KEY-----'\n", encoding="utf-8")
    monkeypatch.setattr(qa_repo_secrets, "_tracked_files", lambda _root: [Path("src/secret.py")])

    failures = qa_repo_secrets.scan_repo(tmp_path)

    assert failures == ["possible committed secret (private-key-block) in src/secret.py"]


def test_repo_secret_scan_allows_documented_examples_and_tests(tmp_path, monkeypatch):
    env_example = tmp_path / ".env.example"
    env_example.write_text("FREEMAIL_ADMIN_API_TOKEN=\n", encoding="utf-8")
    fixture = tmp_path / "tests" / "fixture.py"
    fixture.parent.mkdir()
    fixture.write_text("KEY = '-----BEGIN PRIVATE KEY-----\\ntest\\n-----END PRIVATE KEY-----'\n", encoding="utf-8")
    monkeypatch.setattr(qa_repo_secrets, "_tracked_files", lambda _root: [Path(".env.example"), Path("tests/fixture.py")])

    assert qa_repo_secrets.scan_repo(tmp_path) == []
