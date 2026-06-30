import json
import subprocess
import sys

from freemail_api.open_source_readiness import OpenSourceReadinessOptions, check_open_source_readiness


def test_open_source_readiness_passes_for_current_repo():
    payload = check_open_source_readiness(OpenSourceReadinessOptions())

    assert payload["passed"] is True
    assert payload["license"] == "AGPL-3.0-or-later"
    assert payload["credentialFreePublicRepo"] is True
    assert payload["releaseReady"] is False
    assert "controlled-domain DNS/mail-flow/private-beta evidence" in payload["releaseBlockers"]
    assert all(check["status"] == "pass" for check in payload["checks"])


def test_open_source_readiness_script_outputs_json():
    result = subprocess.run(
        [sys.executable, "scripts/open_source_readiness.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["project"] == "FreeMail"
    assert payload["passed"] is True


def test_open_source_readiness_reports_missing_required_marker(tmp_path, monkeypatch):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    for path in [
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "THIRD_PARTY_NOTICES.md",
        ".env.example",
        ".gitignore",
        ".github/workflows/ci.yml",
        "apps/mobile/package.json",
        "docs/deployment-vpn.md",
        "docs/release-gates.md",
        "docs/mobile-release.md",
        "docs/release-notes/v0.1.0-private-beta.md",
    ]:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("placeholder", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("FreeMail\n", encoding="utf-8")
    (tmp_path / "apps/mobile/package.json").write_text(
        json.dumps({"license": "AGPL-3.0-or-later", "private": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr("freemail_api.open_source_readiness.scan_repo", lambda _root: [])
    monkeypatch.setattr("freemail_api.open_source_readiness.scan_license_policy", lambda _root: [])
    monkeypatch.setattr("freemail_api.open_source_readiness._tracked_files", lambda _root: [])

    payload = check_open_source_readiness(OpenSourceReadinessOptions(root=tmp_path))

    required_files = next(check for check in payload["checks"] if check["name"] == "required-public-files")
    assert payload["passed"] is False
    assert required_files["status"] == "fail"
    assert any(failure["file"] == "README.md" for failure in required_files["details"]["contentFailures"])
