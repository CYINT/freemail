import hashlib
import json
from pathlib import Path

import pytest

from freemail_api import release_gate
from freemail_api.release_gate import assert_release_gate, ReleaseGateError, ReleaseGateOptions, run_release_gate


def test_release_gate_passes_with_ci_runtime_and_backup_evidence(tmp_path, monkeypatch):
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    restore_drill = tmp_path / "restore-drill-evidence.json"
    mobile_evidence = tmp_path / "mobile-release-evidence.json"
    mobile_app_config = tmp_path / "app.json"
    private_beta_evidence = tmp_path / "private-beta-gate.json"
    release_notes = tmp_path / "release-notes.md"
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"archive")
    write_json(restore_drill, valid_restore_drill_evidence())
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
        if command == ["docker", "compose", "--profile", "web", "--profile", "mail-core", "config", "--format", "json"]:
            return json.dumps(valid_compose_config())
        if command[1:] == ["scripts/qa_repo_secrets.py"]:
            return "repo secret QA passed"
        if command[1:] == ["scripts/qa_license_policy.py"]:
            return "license policy QA passed"
        if command[1:] == ["scripts/qa_open_source_readiness.py"]:
            return "open source readiness passed"
        if command[:3] == ["gh", "run", "list"]:
            return '[{"databaseId":1,"status":"completed","conclusion":"success","workflowName":"CI","url":"url"}]'
        if command[:3] == ["gh", "run", "view"]:
            return json.dumps(valid_ci_jobs())
        raise AssertionError(command)

    def fake_fetch(url):
        if url.endswith("/health"):
            return {"status": "ok", "vpnOnly": True, "release": {"commit": "abc123"}}
        if url.endswith("/deployment"):
            return {"exposure": "vpn-only", "publicInternet": False, "requiredBoundary": "Dragonscale/VPN clients only"}
        if url.endswith("/product/readiness"):
            return valid_product_readiness()
        if url.endswith("/metadata/readiness"):
            return {
                "status": "ready",
                "backend": "sqlite",
                "schemaRevision": "sqlite-schema-v1",
                "checks": [{"name": "domains", "status": "pass", "missingColumns": []}],
            }
        if url.endswith("/apple-app-site-association"):
            return valid_apple_app_site_association()
        return {"status": "ready", "tcpReachable": True, "protocolReady": True}

    monkeypatch.setattr(release_gate, "_command", fake_command)
    monkeypatch.setattr(release_gate, "_check_open_source_readiness", fake_open_source_readiness_check)
    monkeypatch.setattr(release_gate, "_fetch_json", fake_fetch)
    monkeypatch.setattr(release_gate, "_fetch_json_value", lambda _url: valid_assetlinks())
    monkeypatch.setattr(release_gate, "_fetch_headers", lambda _url: valid_security_headers())

    result = run_release_gate(
        ReleaseGateOptions(
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            restore_drill_evidence=restore_drill,
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
    assert checks_by_name["restore-drill-evidence"]["details"]["sha256"] == hashlib.sha256(
        restore_drill.read_bytes()
    ).hexdigest()
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
        "compose-loopback-bindings",
        "repo-secret-scan",
        "license-policy-scan",
        "open-source-readiness",
        "github-ci",
        "ci-required-steps",
        "codecov-upload",
        "metadata-backup",
        "mail-store-backup",
        "restore-drill-evidence",
        "mobile-release-evidence",
        "private-beta-evidence",
        "release-notes",
        "runtime-health",
        "runtime-security-headers",
        "deployment-boundary",
        "product-readiness",
        "metadata-readiness",
        "mail-core-readiness",
        "mobile-apple-app-site-association",
        "mobile-android-assetlinks",
    }


def test_release_gate_fails_without_backup_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(release_gate, "_command", fake_basic_release_command)

    result = run_release_gate(
        ReleaseGateOptions(
            metadata_backup=None,
            mail_store_backup=None,
            restore_drill_evidence=None,
            skip_github_ci=True,
            skip_repo_secret_scan=True,
            skip_license_policy_scan=True,
            skip_release_notes=True,
            skip_mobile_evidence=True,
            skip_private_beta_evidence=True,
            skip_runtime=True,
        )
    )

    assert result["passed"] is False
    assert result["checks"][-1]["name"] == "backup-evidence"


def test_release_gate_reports_failed_codecov_upload(tmp_path, monkeypatch):
    def fake_command(command):
        if command == ["git", "rev-parse", "HEAD"]:
            return "abc123"
        if command == ["git", "status", "--short"]:
            return ""
        if command == ["git", "ls-remote", "origin", "refs/heads/main"]:
            return "abc123\trefs/heads/main"
        if command == ["docker", "compose", "config", "--quiet"]:
            return ""
        if command == ["docker", "compose", "--profile", "web", "--profile", "mail-core", "config", "--format", "json"]:
            return json.dumps(valid_compose_config())
        if command[1:] == ["scripts/qa_repo_secrets.py"]:
            return "repo secret QA passed"
        if command[1:] == ["scripts/qa_license_policy.py"]:
            return "license policy QA passed"
        if command[1:] == ["scripts/qa_open_source_readiness.py"]:
            return "open source readiness passed"
        if command[:3] == ["gh", "run", "list"]:
            return '[{"databaseId":1,"status":"completed","conclusion":"success","workflowName":"CI","url":"url"}]'
        if command[:3] == ["gh", "run", "view"]:
            return json.dumps(valid_ci_jobs(step_overrides={"Upload coverage to Codecov": {"conclusion": "failure"}}))
        raise AssertionError(command)

    monkeypatch.setattr(release_gate, "_command", fake_command)
    monkeypatch.setattr(release_gate, "_check_open_source_readiness", fake_open_source_readiness_check)

    result = run_release_gate(
        ReleaseGateOptions(
            skip_backup_evidence=True,
            skip_mobile_evidence=True,
            skip_private_beta_evidence=True,
            skip_release_notes=True,
            skip_runtime=True,
        )
    )

    checks_by_name = {check["name"]: check for check in result["checks"]}
    assert result["passed"] is False
    assert checks_by_name["github-ci"]["status"] == "pass"
    assert checks_by_name["ci-required-steps"]["status"] == "pass"
    assert checks_by_name["codecov-upload"]["status"] == "fail"


def test_release_gate_reports_missing_required_ci_steps(tmp_path, monkeypatch):
    def fake_command(command):
        if command == ["git", "rev-parse", "HEAD"]:
            return "abc123"
        if command == ["git", "status", "--short"]:
            return ""
        if command == ["git", "ls-remote", "origin", "refs/heads/main"]:
            return "abc123\trefs/heads/main"
        if command == ["docker", "compose", "config", "--quiet"]:
            return ""
        if command == ["docker", "compose", "--profile", "web", "--profile", "mail-core", "config", "--format", "json"]:
            return json.dumps(valid_compose_config())
        if command[1:] == ["scripts/qa_repo_secrets.py"]:
            return "repo secret QA passed"
        if command[1:] == ["scripts/qa_license_policy.py"]:
            return "license policy QA passed"
        if command[:3] == ["gh", "run", "list"]:
            return '[{"databaseId":1,"status":"completed","conclusion":"success","workflowName":"CI","url":"url"}]'
        if command[:3] == ["gh", "run", "view"]:
            return json.dumps(valid_ci_jobs(omit_steps={"Mobile native prebuild drill"}))
        raise AssertionError(command)

    monkeypatch.setattr(release_gate, "_command", fake_command)

    result = run_release_gate(
        ReleaseGateOptions(
            skip_codecov_upload=True,
            skip_backup_evidence=True,
            skip_mobile_evidence=True,
            skip_private_beta_evidence=True,
            skip_release_notes=True,
            skip_runtime=True,
        )
    )

    checks_by_name = {check["name"]: check for check in result["checks"]}
    assert result["passed"] is False
    assert checks_by_name["ci-required-steps"]["status"] == "fail"
    assert checks_by_name["ci-required-steps"]["details"]["missingSteps"] == ["Mobile native prebuild drill"]


def test_release_gate_can_skip_codecov_upload_when_ci_is_still_required(tmp_path, monkeypatch):
    def fake_command(command):
        if command == ["git", "rev-parse", "HEAD"]:
            return "abc123"
        if command == ["git", "status", "--short"]:
            return ""
        if command == ["git", "ls-remote", "origin", "refs/heads/main"]:
            return "abc123\trefs/heads/main"
        if command == ["docker", "compose", "config", "--quiet"]:
            return ""
        if command == ["docker", "compose", "--profile", "web", "--profile", "mail-core", "config", "--format", "json"]:
            return json.dumps(valid_compose_config())
        if command[1:] == ["scripts/qa_repo_secrets.py"]:
            return "repo secret QA passed"
        if command[1:] == ["scripts/qa_license_policy.py"]:
            return "license policy QA passed"
        if command[:3] == ["gh", "run", "list"]:
            return '[{"databaseId":1,"status":"completed","conclusion":"success","workflowName":"CI","url":"url"}]'
        if command[:3] == ["gh", "run", "view"]:
            return json.dumps(valid_ci_jobs())
        raise AssertionError(command)

    monkeypatch.setattr(release_gate, "_command", fake_command)
    monkeypatch.setattr(release_gate, "_check_open_source_readiness", fake_open_source_readiness_check)

    result = run_release_gate(
        ReleaseGateOptions(
            skip_codecov_upload=True,
            skip_backup_evidence=True,
            skip_mobile_evidence=True,
            skip_private_beta_evidence=True,
            skip_release_notes=True,
            skip_runtime=True,
        )
    )

    check_names = {check["name"] for check in result["checks"]}
    assert result["passed"] is True
    assert "github-ci" in check_names
    assert "codecov-upload" not in check_names


def test_release_gate_reports_failed_open_source_readiness(monkeypatch):
    monkeypatch.setattr(release_gate, "_command", fake_basic_release_command)
    monkeypatch.setattr(
        release_gate,
        "_check_open_source_readiness",
        lambda: {
            "name": "open-source-readiness",
            "status": "fail",
            "details": {"failedChecks": ["required-public-files"]},
        },
    )

    result = run_release_gate(
        ReleaseGateOptions(
            skip_github_ci=True,
            skip_repo_secret_scan=True,
            skip_license_policy_scan=True,
            skip_backup_evidence=True,
            skip_mobile_evidence=True,
            skip_private_beta_evidence=True,
            skip_release_notes=True,
            skip_runtime=True,
        )
    )

    check = next(check for check in result["checks"] if check["name"] == "open-source-readiness")
    assert result["passed"] is False
    assert check["details"]["failedChecks"] == ["required-public-files"]


def test_release_gate_can_skip_open_source_readiness(monkeypatch):
    monkeypatch.setattr(release_gate, "_command", fake_basic_release_command)

    result = run_release_gate(
        ReleaseGateOptions(
            skip_github_ci=True,
            skip_repo_secret_scan=True,
            skip_license_policy_scan=True,
            skip_open_source_readiness=True,
            skip_backup_evidence=True,
            skip_mobile_evidence=True,
            skip_private_beta_evidence=True,
            skip_release_notes=True,
            skip_runtime=True,
        )
    )

    assert result["passed"] is True
    assert "open-source-readiness" not in {check["name"] for check in result["checks"]}


def test_release_gate_fails_without_mobile_release_evidence(tmp_path, monkeypatch):
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    restore_drill = tmp_path / "restore-drill-evidence.json"
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"archive")
    write_json(restore_drill, valid_restore_drill_evidence())
    monkeypatch.setattr(release_gate, "_command", fake_basic_release_command)

    result = run_release_gate(
        ReleaseGateOptions(
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            restore_drill_evidence=restore_drill,
            skip_github_ci=True,
            skip_repo_secret_scan=True,
            skip_license_policy_scan=True,
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
    monkeypatch.setattr(release_gate, "_command", fake_basic_release_command)

    result = run_release_gate(
        ReleaseGateOptions(
            mobile_release_evidence=mobile_evidence,
            mobile_app_config=mobile_app_config,
            skip_github_ci=True,
            skip_repo_secret_scan=True,
            skip_license_policy_scan=True,
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
    monkeypatch.setattr(release_gate, "_command", fake_basic_release_command)

    result = run_release_gate(
        ReleaseGateOptions(
            skip_github_ci=True,
            skip_repo_secret_scan=True,
            skip_license_policy_scan=True,
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
    monkeypatch.setattr(release_gate, "_command", fake_basic_release_command)

    result = run_release_gate(
        ReleaseGateOptions(
            private_beta_evidence=private_beta_evidence,
            skip_github_ci=True,
            skip_repo_secret_scan=True,
            skip_license_policy_scan=True,
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
    def fake_command(command):
        if command == ["git", "status", "--short"]:
            return "dirty"
        return fake_basic_release_command(command)

    monkeypatch.setattr(release_gate, "_command", fake_command)

    with pytest.raises(ReleaseGateError, match="git-clean"):
        assert_release_gate(
            ReleaseGateOptions(
                skip_github_ci=True,
                skip_repo_secret_scan=True,
                skip_license_policy_scan=True,
                skip_backup_evidence=True,
                skip_mobile_evidence=True,
                skip_private_beta_evidence=True,
                skip_release_notes=True,
                skip_runtime=True,
            )
        )


def test_runtime_health_requires_exact_candidate_commit(monkeypatch):
    monkeypatch.setattr(release_gate, "_fetch_json", lambda _url: {"status": "ok", "vpnOnly": True, "release": {"commit": "unknown"}})
    monkeypatch.setattr(release_gate, "_fetch_headers", lambda _url: valid_security_headers())

    checks = release_gate._check_runtime("https://freemail.kuzuryu.ai/health", None, None, "abc123")

    assert checks[0]["name"] == "runtime-health"
    assert checks[0]["status"] == "fail"
    assert checks[0]["details"]["releaseCommit"] == "unknown"


def test_runtime_security_headers_require_csp(monkeypatch):
    headers = valid_security_headers()
    headers.pop("content-security-policy")
    monkeypatch.setattr(release_gate, "_fetch_json", lambda _url: {"status": "ok", "vpnOnly": True, "release": {"commit": "abc123"}})
    monkeypatch.setattr(release_gate, "_fetch_headers", lambda _url: headers)

    checks = release_gate._check_runtime("https://freemail.kuzuryu.ai/health", None, None, "abc123")
    checks_by_name = {check["name"]: check for check in checks}

    assert checks_by_name["runtime-health"]["status"] == "pass"
    assert checks_by_name["runtime-security-headers"]["status"] == "fail"
    assert "content-security-policy" in checks_by_name["runtime-security-headers"]["details"]["missing"]


def test_runtime_deployment_boundary_requires_vpn_only(monkeypatch):
    monkeypatch.setattr(
        release_gate,
        "_fetch_json",
        lambda _url: {"exposure": "public", "publicInternet": True, "requiredBoundary": "internet"},
    )

    checks = release_gate._check_runtime(None, "https://freemail.kuzuryu.ai/api/v1/deployment", None, "abc123")

    assert checks[0]["name"] == "deployment-boundary"
    assert checks[0]["status"] == "fail"


def test_runtime_product_readiness_requires_expected_component_statuses(monkeypatch):
    payload = valid_product_readiness()
    payload["components"]["mobile"]["status"] = "prototype"
    monkeypatch.setattr(release_gate, "_fetch_json", lambda _url: payload)

    checks = release_gate._check_runtime(
        None,
        None,
        None,
        "abc123",
        product_readiness_url="https://freemail.kuzuryu.ai/api/v1/product/readiness",
    )

    assert checks[0]["name"] == "product-readiness"
    assert checks[0]["status"] == "fail"
    assert checks[0]["details"]["componentStatuses"]["mobile"] == "prototype"


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


def test_runtime_mobile_apple_association_requires_invite_component(monkeypatch):
    payload = valid_apple_app_site_association()
    payload["applinks"]["details"][0]["components"] = [{"/": "/*"}]
    monkeypatch.setattr(release_gate, "_fetch_json", lambda _url: payload)

    check = release_gate._check_apple_app_site_association(
        "https://freemail.kuzuryu.ai/.well-known/apple-app-site-association"
    )

    assert check["name"] == "mobile-apple-app-site-association"
    assert check["status"] == "fail"
    assert check["details"]["hasInviteComponent"] is False


def test_runtime_mobile_android_assetlinks_requires_valid_fingerprint(monkeypatch):
    payload = valid_assetlinks()
    payload[0]["target"]["sha256_cert_fingerprints"] = ["not-a-fingerprint"]
    monkeypatch.setattr(release_gate, "_fetch_json_value", lambda _url: payload)

    check = release_gate._check_assetlinks("https://freemail.kuzuryu.ai/.well-known/assetlinks.json")

    assert check["name"] == "mobile-android-assetlinks"
    assert check["status"] == "fail"
    assert check["details"]["validFingerprintCount"] == 0


def test_compose_loopback_bindings_accepts_loopback_published_ports(monkeypatch):
    monkeypatch.setattr(release_gate, "_command", lambda _command: json.dumps(valid_compose_config()))

    check = release_gate._check_compose_loopback_bindings()

    assert check["status"] == "pass"
    assert check["details"]["violations"] == []
    assert {binding["service"] for binding in check["details"]["bindings"]} == {"admin-api", "mail-core", "web"}


def test_compose_loopback_bindings_rejects_public_published_ports(monkeypatch):
    payload = valid_compose_config()
    payload["services"]["web"]["ports"][0]["host_ip"] = "0.0.0.0"
    monkeypatch.setattr(release_gate, "_command", lambda _command: json.dumps(payload))

    check = release_gate._check_compose_loopback_bindings()

    assert check["status"] == "fail"
    assert check["details"]["violations"] == [
        {
            "service": "web",
            "hostIp": "0.0.0.0",
            "published": "18091",
            "target": 80,
            "protocol": "tcp",
        }
    ]


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


def test_restore_drill_evidence_check_requires_successful_drill(tmp_path):
    evidence = tmp_path / "restore-drill-evidence.json"
    payload = valid_restore_drill_evidence()
    payload["mailStoreRestore"]["restored"] = False
    write_json(evidence, payload)

    check = release_gate._check_restore_drill_evidence(evidence)

    assert check["status"] == "fail"
    assert check["details"]["credentialFree"] is True
    assert check["details"]["metadataRestored"] is True
    assert check["details"]["mailStoreRestored"] is False


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
            "scheme": "freemail",
            "ios": {
                "bundleIdentifier": "technology.cyint.freemail",
                "buildNumber": "1",
                "associatedDomains": ["applinks:freemail.kuzuryu.ai"],
            },
            "android": {
                "package": "technology.cyint.freemail",
                "versionCode": 1,
                "intentFilters": [
                    {
                        "action": "VIEW",
                        "autoVerify": True,
                        "data": [{"scheme": "https", "host": "freemail.kuzuryu.ai"}],
                        "category": ["BROWSABLE", "DEFAULT"],
                    }
                ],
            },
            "extra": {"apiBaseUrl": "https://freemail.kuzuryu.ai"},
        }
    }


def fake_open_source_readiness_check():
    return {
        "name": "open-source-readiness",
        "status": "pass",
        "details": {
            "credentialFreePublicRepo": True,
            "license": "AGPL-3.0-or-later",
            "releaseReady": False,
            "releaseBlockers": ["decision-owner private-beta acceptance"],
            "failedChecks": [],
        },
    }


def valid_apple_app_site_association():
    return {
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": "ABCDE12345.technology.cyint.freemail",
                    "components": [
                        {
                            "/": "/invite",
                            "?": {"invite": "*"},
                        }
                    ],
                }
            ],
        }
    }


def valid_assetlinks():
    return [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "technology.cyint.freemail",
                "sha256_cert_fingerprints": [
                    "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"
                ],
            },
        }
    ]


def fake_basic_release_command(command):
    if command == ["git", "rev-parse", "HEAD"]:
        return "abc123"
    if command == ["git", "status", "--short"]:
        return ""
    if command == ["git", "ls-remote", "origin", "refs/heads/main"]:
        return "abc123\trefs/heads/main"
    if command == ["docker", "compose", "config", "--quiet"]:
        return ""
    if command == ["docker", "compose", "--profile", "web", "--profile", "mail-core", "config", "--format", "json"]:
        return json.dumps(valid_compose_config())
    raise AssertionError(command)


def valid_ci_jobs(*, omit_steps=None, step_overrides=None):
    omitted = set(omit_steps or set())
    overrides = step_overrides or {}
    steps = []
    for name in [*release_gate.REQUIRED_CI_STEPS, "Upload coverage to Codecov"]:
        if name in omitted:
            continue
        step = {"name": name, "status": "completed", "conclusion": "success"}
        step.update(overrides.get(name, {}))
        steps.append(step)
    return {"jobs": [{"name": "test", "steps": steps}]}


def valid_compose_config():
    return {
        "services": {
            "admin-api": {
                "ports": [
                    {
                        "host_ip": "127.0.0.1",
                        "published": "18090",
                        "target": 8080,
                        "protocol": "tcp",
                    }
                ]
            },
            "mail-core": {
                "ports": [
                    {
                        "host_ip": "127.0.0.1",
                        "published": "2525",
                        "target": 25,
                        "protocol": "tcp",
                    },
                    {
                        "host_ip": "127.0.0.1",
                        "published": "2465",
                        "target": 465,
                        "protocol": "tcp",
                    },
                ]
            },
            "web": {
                "ports": [
                    {
                        "host_ip": "127.0.0.1",
                        "published": "18091",
                        "target": 80,
                        "protocol": "tcp",
                    }
                ]
            },
        }
    }


def valid_product_readiness():
    return {
        "project": "FreeMail",
        "license": "AGPL-3.0-or-later",
        "credentialFreePublicRepo": True,
        "vpnOnly": True,
        "releaseReady": False,
        "components": {
            "adminApi": {"status": "ready"},
            "mailCore": {"status": "runtime-ready"},
            "webmail": {"status": "beta-ready"},
            "mobile": {"status": "source-ready"},
        },
        "releaseBlockers": [
            "decision-owner private-beta acceptance",
            "real signed native mobile builds",
        ],
    }


def valid_security_headers():
    return {
        "content-security-policy": (
            "default-src 'self'; base-uri 'self'; "
            "connect-src 'self' http://127.0.0.1:18090 https://freemail.kuzuryu.ai; "
            "form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; "
            "script-src 'self'; style-src 'self'; upgrade-insecure-requests"
        ),
        "cross-origin-opener-policy": "same-origin",
        "permissions-policy": "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
        "referrer-policy": "no-referrer",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
    }


def valid_mobile_release_evidence():
    return {
        "app": {
            "name": "FreeMail",
            "version": "0.1.0-dev",
            "apiBaseUrl": "https://freemail.kuzuryu.ai",
        },
        "nativeBuilds": {"ios": "1", "android": "1"},
        "builds": {
            "ios": {
                "identifier": "technology.cyint.freemail",
                "nativeBuildId": "1",
                "signed": True,
                "distribution": "private-beta",
                "buildUrl": "https://example.invalid/ios-build",
                "artifact": {"type": "ipa", "bytes": 123, "sha256": "a" * 64},
            },
            "android": {
                "identifier": "technology.cyint.freemail",
                "nativeBuildId": "1",
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
                "nativeBuildId": "1",
                "track": "testflight",
                "submitted": True,
                "submissionUrl": "https://example.invalid/testflight",
                "submittedAt": "2026-06-30T00:00:00Z",
                "reviewState": "processing",
            },
            "android": {
                "store": "play-console",
                "identifier": "technology.cyint.freemail",
                "nativeBuildId": "1",
                "track": "internal-testing",
                "submitted": True,
                "submissionUrl": "https://example.invalid/play-internal",
                "submittedAt": "2026-06-30T00:00:00Z",
                "reviewState": "draft-release-created",
            },
        },
        "deviceValidation": {
            "ios": valid_mobile_device_validation("ios"),
            "android": valid_mobile_device_validation("android"),
        },
        "privateBetaBoundary": {
            "hostname": "freemail.kuzuryu.ai",
            "vpnOnly": True,
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        },
    }


def valid_mobile_device_validation(platform):
    return {
        "platform": platform,
        "tested": True,
        "testedAt": "2026-06-30T00:00:00Z",
        "tester": "release operator",
        "deviceModel": "iPhone 15" if platform == "ios" else "Pixel 8",
        "osVersion": "iOS 18" if platform == "ios" else "Android 15",
        "appVersion": "0.1.0-dev",
        "hostname": "freemail.kuzuryu.ai",
        "networkBoundary": "Dragonscale/VPN clients only",
        "evidenceUrl": f"https://example.invalid/{platform}-device-validation",
        "checks": [
            {"name": "vpn-dns-resolution", "status": "pass"},
            {"name": "auth-login", "status": "pass"},
            {"name": "inbox-sync", "status": "pass"},
            {"name": "message-read", "status": "pass"},
            {"name": "compose-send", "status": "pass"},
            {"name": "invite-link-open", "status": "pass"},
            {"name": "offline-cache", "status": "pass"},
        ],
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
            {"name": "restore-drill-evidence", "status": "pass", "details": {}},
            {"name": "private-beta-acceptance", "status": "pass", "details": {}},
        ],
    }


def valid_restore_drill_evidence():
    return {
        "credentialFree": True,
        "metadataRestore": {"restored": True, "tableCounts": {"domains": 1}},
        "mailStoreRestore": {"restored": True, "drillVolume": "freemail_stalwart_restore_drill"},
        "stalwartApplyPlan": {"exported": True, "summary": {"operations": 1}},
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
