import json
import subprocess
import sys

from freemail_api.mobile_release_status import summarize_mobile_release_evidence


def test_mobile_release_status_reports_missing_evidence(tmp_path):
    evidence = tmp_path / "missing.json"
    app_config = tmp_path / "app.json"
    write_app_config(app_config)

    result = summarize_mobile_release_evidence(evidence=evidence, app_config=app_config, require_store_submission=True)

    assert result["ready"] is False
    assert result["failedChecks"] == ["mobile-release-evidence"]
    assert result["checks"][0]["details"]["status"] == "missing"


def test_mobile_release_status_reports_failed_gate_checks_for_draft(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release-evidence.json"
    write_app_config(app_config)
    write_json(
        evidence,
        {
            "app": {"name": "FreeMail", "version": "0.1.0-dev", "apiBaseUrl": "https://freemail.kuzuryu.ai"},
            "builds": {
                "ios": {"identifier": "technology.cyint.freemail", "signed": False, "artifact": {}},
                "android": {"identifier": "technology.cyint.freemail", "signed": False, "artifact": {}},
            },
            "privateBetaBoundary": {
                "hostname": "freemail.kuzuryu.ai",
                "vpnOnly": True,
                "publicInternet": False,
                "requiredBoundary": "Dragonscale/VPN clients only",
            },
        },
    )

    result = summarize_mobile_release_evidence(evidence=evidence, app_config=app_config, require_store_submission=True)

    assert result["ready"] is False
    assert result["failedChecks"] == [
        "ios-signed-build",
        "android-signed-build",
        "ios-store-submission",
        "android-store-submission",
    ]
    assert result["evidenceDetails"]["sha256"]


def test_mobile_release_status_accepts_complete_store_submission_packet(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release-evidence.json"
    write_app_config(app_config)
    write_json(evidence, complete_evidence())

    result = summarize_mobile_release_evidence(evidence=evidence, app_config=app_config, require_store_submission=True)

    assert result["ready"] is True
    assert result["failedChecks"] == []
    assert [check["status"] for check in result["checks"]] == ["pass"] * 7


def test_mobile_release_status_script_exits_nonzero_until_ready(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release-evidence.json"
    write_app_config(app_config)
    write_json(evidence, complete_evidence() | {"storeSubmissions": {}})

    result = subprocess.run(
        [
            sys.executable,
            "scripts/mobile_release_status.py",
            "--evidence",
            str(evidence),
            "--app-config",
            str(app_config),
            "--require-store-submission",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert payload["failedChecks"] == ["ios-store-submission", "android-store-submission"]


def write_app_config(path):
    write_json(
        path,
        {
            "expo": {
                "name": "FreeMail",
                "version": "0.1.0-dev",
                "ios": {"bundleIdentifier": "technology.cyint.freemail"},
                "android": {"package": "technology.cyint.freemail"},
                "extra": {"apiBaseUrl": "https://freemail.kuzuryu.ai"},
            }
        },
    )


def complete_evidence():
    return {
        "app": {"name": "FreeMail", "version": "0.1.0-dev", "apiBaseUrl": "https://freemail.kuzuryu.ai"},
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


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
