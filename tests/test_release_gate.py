from pathlib import Path

import pytest

from freemail_api import release_gate
from freemail_api.release_gate import assert_release_gate, ReleaseGateError, ReleaseGateOptions, run_release_gate


def test_release_gate_passes_with_ci_runtime_and_backup_evidence(tmp_path, monkeypatch):
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"archive")

    def fake_command(command):
        if command == ["git", "rev-parse", "HEAD"]:
            return "abc123"
        if command == ["git", "status", "--short"]:
            return ""
        if command == ["git", "ls-remote", "origin", "refs/heads/main"]:
            return "abc123\trefs/heads/main"
        if command == ["docker", "compose", "config", "--quiet"]:
            return ""
        if command[:3] == ["gh", "run", "list"]:
            return '[{"databaseId":1,"status":"completed","conclusion":"success","workflowName":"CI","url":"url"}]'
        raise AssertionError(command)

    def fake_fetch(url):
        if url.endswith("/health"):
            return {"status": "ok", "vpnOnly": True, "release": {"commit": "abc123"}}
        return {"status": "ready", "tcpReachable": True, "protocolReady": True}

    monkeypatch.setattr(release_gate, "_command", fake_command)
    monkeypatch.setattr(release_gate, "_fetch_json", fake_fetch)

    result = run_release_gate(ReleaseGateOptions(metadata_backup=metadata, mail_store_backup=mail_store))

    assert result["passed"] is True
    assert {check["name"] for check in result["checks"]} == {
        "git-clean",
        "remote-sha",
        "compose-config",
        "github-ci",
        "metadata-backup",
        "mail-store-backup",
        "runtime-health",
        "mail-core-readiness",
    }


def test_release_gate_fails_without_backup_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(release_gate, "_command", lambda command: "abc123" if command[-1] == "HEAD" else "")

    result = run_release_gate(
        ReleaseGateOptions(
            metadata_backup=None,
            mail_store_backup=None,
            skip_github_ci=True,
            skip_runtime=True,
        )
    )

    assert result["passed"] is False
    assert result["checks"][-1]["name"] == "backup-evidence"


def test_assert_release_gate_raises_for_failed_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(release_gate, "_command", lambda command: "dirty" if command == ["git", "status", "--short"] else "abc123")

    with pytest.raises(ReleaseGateError, match="git-clean"):
        assert_release_gate(
            ReleaseGateOptions(
                skip_github_ci=True,
                skip_backup_evidence=True,
                skip_runtime=True,
            )
        )


def test_runtime_health_accepts_unknown_commit_for_unstamped_local_container(monkeypatch):
    monkeypatch.setattr(release_gate, "_fetch_json", lambda _url: {"status": "ok", "vpnOnly": True, "release": {"commit": "unknown"}})

    checks = release_gate._check_runtime("https://freemail.kuzuryu.ai/health", None, "abc123")

    assert checks[0]["status"] == "pass"


def test_backup_file_check_requires_non_empty_file(tmp_path):
    missing = Path(tmp_path / "missing.tar.gz")
    empty = tmp_path / "empty.tar.gz"
    empty.write_bytes(b"")

    assert release_gate._check_backup_file("missing", missing)["status"] == "fail"
    assert release_gate._check_backup_file("empty", empty)["status"] == "fail"
