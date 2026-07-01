from datetime import datetime, timezone
import json
import subprocess
import sys

import pytest

from freemail_api.mobile_release_evidence import (
    MobileReleaseEvidenceTemplateOptions,
    create_mobile_release_evidence_template,
)
from freemail_api.mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate


def test_mobile_release_evidence_template_uses_app_config_and_failing_defaults(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(
        app_config,
        {
            "expo": {
                "name": "FreeMail",
                "version": "0.1.0-dev",
                "ios": {"buildNumber": "1"},
                "android": {"versionCode": 1},
                "extra": {"apiBaseUrl": "https://freemail.kuzuryu.ai"},
            }
        },
    )

    result = create_mobile_release_evidence_template(
        MobileReleaseEvidenceTemplateOptions(
            output=evidence,
            app_config=app_config,
            generated_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))

    assert result["generatedAt"] == "2026-06-30T00:00:00Z"
    assert payload["app"]["name"] == "FreeMail"
    assert payload["app"]["version"] == "0.1.0-dev"
    assert payload["app"]["apiBaseUrl"] == "https://freemail.kuzuryu.ai"
    assert payload["nativeBuilds"] == {"ios": "1", "android": "1"}
    assert payload["builds"]["ios"]["identifier"] == "technology.cyint.freemail"
    assert payload["builds"]["ios"]["nativeBuildId"] == "1"
    assert payload["builds"]["ios"]["signed"] is False
    assert payload["builds"]["android"]["artifact"]["type"] == "aab"
    assert payload["storeSubmissions"]["android"]["nativeBuildId"] == "1"
    assert payload["storeSubmissions"]["ios"]["submitted"] is False
    assert payload["deviceValidation"]["ios"]["tested"] is False
    assert payload["deviceValidation"]["android"]["checks"][0]["name"] == "vpn-dns-resolution"
    assert {"name": "invite-link-open", "status": "pending"} in payload["deviceValidation"]["ios"]["checks"]
    assert payload["privateBetaBoundary"]["vpnOnly"] is True


def test_mobile_release_evidence_template_does_not_accidentally_pass_gate(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(
        app_config,
        {
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
        },
    )
    create_mobile_release_evidence_template(
        MobileReleaseEvidenceTemplateOptions(
            output=evidence,
            app_config=app_config,
            generated_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
    )

    result = run_mobile_release_gate(
        MobileReleaseGateOptions(evidence=evidence, app_config=app_config, require_store_submission=True)
    )

    checks = {check["name"]: check for check in result["checks"]}
    assert result["passed"] is False
    assert checks["no-signing-secrets"]["status"] == "pass"
    assert checks["app-metadata"]["status"] == "pass"
    assert checks["private-beta-boundary"]["status"] == "pass"
    assert checks["ios-signed-build"]["status"] == "fail"
    assert checks["android-signed-build"]["status"] == "fail"
    assert checks["ios-device-validation"]["status"] == "fail"
    assert checks["android-device-validation"]["status"] == "fail"
    assert checks["ios-store-submission"]["status"] == "fail"
    assert checks["android-store-submission"]["status"] == "fail"


def test_mobile_release_evidence_template_refuses_overwrite_without_force(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(app_config, {"expo": {"name": "FreeMail"}})
    options = MobileReleaseEvidenceTemplateOptions(
        output=evidence,
        app_config=app_config,
        generated_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )
    create_mobile_release_evidence_template(options)

    with pytest.raises(FileExistsError):
        create_mobile_release_evidence_template(options)


def test_mobile_release_evidence_template_script(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/create_mobile_release_evidence_template.py",
            "--output",
            str(evidence),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["file"] == str(evidence)
    assert evidence.is_file()


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
