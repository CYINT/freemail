import hashlib
import json
from pathlib import Path

import pytest

from freemail_api import release_gate
from freemail_api.release_gate import assert_release_gate, ReleaseGateError, ReleaseGateOptions, run_release_gate


def test_release_gate_passes_with_ci_runtime_and_backup_evidence(tmp_path, monkeypatch):
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    mobile_evidence = tmp_path / "mobile-release-evidence.json"
    mobile_app_config = tmp_path / "app.json"
    private_beta_evidence = tmp_path / "private-beta-gate.json"
    release_notes = tmp_path / "release-notes.md"
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"archive")
    write_json(mobile_app_config, valid_mobile_app_config())
    write_json(mobile_evidence, valid_mobile_release_evidence())
    write_json(private_beta_evidence, valid_private_beta_evidence())
    release_notes.write_text(
        "# FreeMail v0.1.0-private-beta\n\n"
        "Verification: CI, release gates, and backup evidence passed.\n\n"
        "Known limitations: VPN-only private beta.\n",
        encoding="utf-8",
    )

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
        if url.endswith("/deployment"):
            return {"exposure": "vpn-only", "publicInternet": False, "requiredBoundary": "Dragonscale/VPN clients only"}
        if url.endswith("/metadata/readiness"):
            return {
                "status": "ready",
                "backend": "sqlite",
                "schemaRevision": "sqlite-schema-v1",
                "checks": [{"name": "domains", "status": "pass", "missingColumns": []}],
            }
        return {"status": "ready", "tcpReachable": True, "protocolReady": True}

    monkeypatch.setattr(release_gate, "_command", fake_command)
    monkeypatch.setattr(release_gate, "_fetch_json", fake_fetch)

    result = run_release_gate(
        ReleaseGateOptions(
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            mobile_release_evidence=mobile_evidence,
            mobile_app_config=mobile_app_config,
            require_mobile_store_submission=True,
            private_beta_evidence=private_beta_evidence,
            release_notes=release_notes,
            release_version="v0.1.0-private-beta",
        )
    )

    assert result["passed"] is True
    checks_by_name = {check["name"]: check for check in result["checks"]}
    assert checks_by_name["metadata-backup"]["details"]["sha256"] == hashlib.sha256(b"{}").hexdigest()
    assert checks_by_name["mail-store-backup"]["details"]["sha256"] == hashlib.sha256(b"archive").hexdigest()
    assert checks_by_name["mobile-release-evidence"]["details"]["evidenceDetails"]["sha256"] == hashlib.sha256(
        mobile_evidence.read_bytes()
    ).hexdigest()
    assert checks_by_name["private-beta-evidence"]["details"]["sha256"] == hashlib.sha256(
        private_beta_evidence.read_bytes()
    ).hexdigest()
    assert checks_by_name["release-notes"]["details"]["sha256"] == hashlib.sha256(
        release_notes.read_bytes()
    ).hexdigest()
    assert {check["name"] for check in result["checks"]} == {
        "git-clean",
        "remote-sha",
        "compose-config",
        "github-ci",
        "metadata-backup",
        "mail-store-backup",
        "mobile-release-evidence",
        "private-beta-evidence",
        "release-notes",
        "runtime-health",
        "deployment-boundary",
        "metadata-readiness",
        "mail-core-readiness",
    }


def test_release_gate_fails_without_backup_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(release_gate, "_command", lambda command: "abc123" if command[-1] == "HEAD" else "")

    result = run_release_gate(
        ReleaseGateOptions(
            metadata_backup=None,
            mail_store_backup=None,
            skip_github_ci=True,
            skip_release_notes=True,
            skip_mobile_evidence=True,
            skip_private_beta_evidence=True,
            skip_runtime=True,
        )
    )

    assert result["passed"] is False
    assert result["checks"][-1]["name"] == "backup-evidence"


def test_release_gate_fails_without_mobile_release_evidence(tmp_path, monkeypatch):
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"archive")
    monkeypatch.setattr(release_gate, "_command", lambda command: "abc123" if command[-1] == "HEAD" else "")

    result = run_release_gate(
        ReleaseGateOptions(
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            skip_github_ci=True,
            skip_release_notes=True,
            skip_runtime=True,
        )
    )

    checks_by_name = {check["name"]: check for check in result["checks"]}
    assert result["passed"] is False
    assert checks_by_name["mobile-release-evidence"]["status"] == "fail"
    assert "required" in checks_by_name["mobile-release-evidence"]["details"]["error"]


def test_release_gate_reports_failed_mobile_release_evidence(tmp_path, monkeypatch):
    mobile_evidence = tmp_path / "mobile-release-evidence.json"
    mobile_app_config = tmp_path / "app.json"
    write_json(mobile_app_config, valid_mobile_app_config())
    payload = valid_mobile_release_evidence()
    payload["builds"]["ios"]["signed"] = False
    write_json(mobile_evidence, payload)
    monkeypatch.setattr(release_gate, "_command", lambda command: "abc123" if command[-1] == "HEAD" else "")

    result = run_release_gate(
        ReleaseGateOptions(
            mobile_release_evidence=mobile_evidence,
            mobile_app_config=mobile_app_config,
            skip_github_ci=True,
            skip_backup_evidence=True,
            skip_release_notes=True,
            skip_runtime=True,
        )
    )

    check = next(check for check in result["checks"] if check["name"] == "mobile-release-evidence")
    assert result["passed"] is False
    assert check["status"] == "fail"
    assert check["details"]["failedChecks"] == ["ios-signed-build"]


def test_release_gate_fails_without_private_beta_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(release_gate, "_command", lambda command: "abc123" if command[-1] == "HEAD" else "")

    result = run_release_gate(
        ReleaseGateOptions(
            skip_github_ci=True,
            skip_backup_evidence=True,
            skip_mobile_evidence=True,
            skip_release_notes=True,
            skip_runtime=True,
        )
    )

    check = next(check for check in result["checks"] if check["name"] == "private-beta-evidence")
    assert result["passed"] is False
    assert check["status"] == "fail"
    assert "required" in check["details"]["error"]


def test_release_gate_reports_failed_private_beta_evidence(tmp_path, monkeypatch):
    private_beta_evidence = tmp_path / "private-beta-gate.json"
    payload = valid_private_beta_evidence()
    payload["checks"][2]["status"] = "fail"
    write_json(private_beta_evidence, payload)
    monkeypatch.setattr(release_gate, "_command", lambda command: "abc123" if command[-1] == "HEAD" else "")

    result = run_release_gate(
        ReleaseGateOptions(
            private_beta_evidence=private_beta_evidence,
            skip_github_ci=True,
            skip_backup_evidence=True,
            skip_mobile_evidence=True,
            skip_release_notes=True,
            skip_runtime=True,
        )
    )

    check = next(check for check in result["checks"] if check["name"] == "private-beta-evidence")
    assert result["passed"] is False
    assert check["status"] == "fail"
    assert check["details"]["failedChecks"] == ["queue-evidence"]


def test_assert_release_gate_raises_for_failed_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(release_gate, "_command", lambda command: "dirty" if command == ["git", "status", "--short"] else "abc123")

    with pytest.raises(ReleaseGateError, match="git-clean"):
        assert_release_gate(
            ReleaseGateOptions(
                skip_github_ci=True,
                skip_backup_evidence=True,
                skip_mobile_evidence=True,
                skip_private_beta_evidence=True,
                skip_release_notes=True,
                skip_runtime=True,
            )
        )


def test_runtime_health_accepts_unknown_commit_for_unstamped_local_container(monkeypatch):
    monkeypatch.setattr(release_gate, "_fetch_json", lambda _url: {"status": "ok", "vpnOnly": True, "release": {"commit": "unknown"}})

    checks = release_gate._check_runtime("https://freemail.kuzuryu.ai/health", None, None, "abc123")

    assert checks[0]["status"] == "pass"


def test_runtime_deployment_boundary_requires_vpn_only(monkeypatch):
    monkeypatch.setattr(
        release_gate,
        "_fetch_json",
        lambda _url: {"exposure": "public", "publicInternet": True, "requiredBoundary": "internet"},
    )

    checks = release_gate._check_runtime(None, "https://freemail.kuzuryu.ai/api/v1/deployment", None, "abc123")

    assert checks[0]["name"] == "deployment-boundary"
    assert checks[0]["status"] == "fail"


def test_runtime_metadata_readiness_requires_ready_sqlite_schema(monkeypatch):
    monkeypatch.setattr(
        release_gate,
        "_fetch_json",
        lambda _url: {
            "status": "not-ready",
            "backend": "sqlite",
            "schemaRevision": "sqlite-schema-v1",
            "checks": [{"name": "users", "status": "fail", "missingColumns": ["status"]}],
        },
    )

    checks = release_gate._check_runtime(
        None,
        None,
        None,
        "abc123",
        metadata_readiness_url="https://freemail.kuzuryu.ai/api/v1/metadata/readiness",
    )

    assert checks[0]["name"] == "metadata-readiness"
    assert checks[0]["status"] == "fail"
    assert checks[0]["details"]["checks"][0]["missingColumns"] == ["status"]


def test_backup_file_check_requires_non_empty_file(tmp_path):
    missing = Path(tmp_path / "missing.tar.gz")
    empty = tmp_path / "empty.tar.gz"
    empty.write_bytes(b"")

    assert release_gate._check_backup_file("missing", missing)["status"] == "fail"
    assert release_gate._check_backup_file("empty", empty)["status"] == "fail"


def test_backup_file_check_records_sha256_for_non_empty_file(tmp_path):
    archive = tmp_path / "mail-store.tar.gz"
    archive.write_bytes(b"backup")

    check = release_gate._check_backup_file("mail-store-backup", archive)

    assert check["status"] == "pass"
    assert check["details"]["bytes"] == 6
    assert check["details"]["sha256"] == hashlib.sha256(b"backup").hexdigest()


def test_release_notes_check_requires_version_and_required_sections(tmp_path):
    release_notes = tmp_path / "release-notes.md"
    release_notes.write_text(
        "# FreeMail v0.1.0-private-beta\n\n"
        "Verification: CI passed.\n\n"
        "Known limitations: VPN-only private beta.\n",
        encoding="utf-8",
    )

    check = release_gate._check_release_notes(release_notes, "v0.1.0-private-beta")

    assert check["status"] == "pass"
    assert check["details"]["versionPresent"] is True
    assert check["details"]["missingRequiredTerms"] == []


def test_release_notes_check_rejects_placeholder_text(tmp_path):
    release_notes = tmp_path / "release-notes.md"
    release_notes.write_text(
        "# FreeMail v0.1.0-private-beta\n\n"
        "Verification: TODO.\n\n"
        "Known limitations: VPN-only private beta.\n",
        encoding="utf-8",
    )

    check = release_gate._check_release_notes(release_notes, "v0.1.0-private-beta")

    assert check["status"] == "fail"
    assert check["details"]["placeholderTerms"] == ["todo"]


def test_release_notes_check_rejects_missing_version(tmp_path):
    release_notes = tmp_path / "release-notes.md"
    release_notes.write_text(
        "# FreeMail private beta\n\n"
        "Verification: CI passed.\n\n"
        "Known limitations: VPN-only private beta.\n",
        encoding="utf-8",
    )

    check = release_gate._check_release_notes(release_notes, "v0.1.0-private-beta")

    assert check["status"] == "fail"
    assert check["details"]["versionPresent"] is False


def valid_mobile_app_config():
    return {
        "expo": {
            "name": "FreeMail",
            "version": "0.1.0-dev",
            "ios": {"bundleIdentifier": "technology.cyint.freemail"},
            "android": {"package": "technology.cyint.freemail"},
            "extra": {"apiBaseUrl": "https://freemail.kuzuryu.ai"},
        }
    }


def valid_mobile_release_evidence():
    return {
        "app": {
            "name": "FreeMail",
            "version": "0.1.0-dev",
            "apiBaseUrl": "https://freemail.kuzuryu.ai",
        },
        "builds": {
            "ios": {
                "identifier": "technology.cyint.freemail",
                "signed": True,
                "distribution": "private-beta",
                "buildUrl": "https://example.invalid/ios-build",
                "artifact": {"type": "ipa", "bytes": 123, "sha256": "a" * 64},
            },
            "android": {
                "identifier": "technology.cyint.freemail",
                "signed": True,
                "distribution": "private-beta",
                "buildUrl": "https://example.invalid/android-build",
                "artifact": {"type": "aab", "bytes": 456, "sha256": "b" * 64},
            },
        },
        "storeSubmissions": {
            "ios": {
                "store": "app-store-connect",
                "identifier": "technology.cyint.freemail",
                "track": "testflight",
                "submitted": True,
                "submissionUrl": "https://example.invalid/testflight",
                "submittedAt": "2026-06-30T00:00:00Z",
                "reviewState": "processing",
            },
            "android": {
                "store": "play-console",
                "identifier": "technology.cyint.freemail",
                "track": "internal-testing",
                "submitted": True,
                "submissionUrl": "https://example.invalid/play-internal",
                "submittedAt": "2026-06-30T00:00:00Z",
                "reviewState": "draft-release-created",
            },
        },
        "privateBetaBoundary": {
            "hostname": "freemail.kuzuryu.ai",
            "vpnOnly": True,
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        },
    }


def valid_private_beta_evidence():
    return {
        "passed": True,
        "domain": "example.com",
        "checks": [
            {"name": "controlled-domain-dns", "status": "pass", "details": {}},
            {"name": "controlled-mail-flow-evidence", "status": "pass", "details": {}},
            {"name": "queue-evidence", "status": "pass", "details": {}},
            {"name": "mail-core-apply-evidence", "status": "pass", "details": {}},
            {"name": "deliverability-abuse-evidence", "status": "pass", "details": {}},
            {"name": "metadata-backup-evidence", "status": "pass", "details": {}},
            {"name": "mail-store-backup-evidence", "status": "pass", "details": {}},
            {"name": "private-beta-acceptance", "status": "pass", "details": {}},
        ],
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
