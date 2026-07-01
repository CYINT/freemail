import json
import os
from pathlib import Path
import subprocess
import sys

from freemail_api.mobile_release_status import summarize_mobile_release_evidence


ROOT = Path(__file__).resolve().parents[1]


def test_mobile_release_status_reports_missing_evidence(tmp_path):
    evidence = tmp_path / "missing.json"
    app_config = tmp_path / "app.json"
    write_app_config(app_config)

    result = summarize_mobile_release_evidence(evidence=evidence, app_config=app_config, require_store_submission=True)

    assert result["ready"] is False
    assert result["failedChecks"] == ["mobile-release-evidence"]
    assert result["checks"][0]["details"]["status"] == "missing"
    assert [action["id"] for action in result["nextActions"]] == ["create-mobile-release-evidence-template"]


def test_mobile_release_status_reports_failed_gate_checks_for_draft(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release-evidence.json"
    write_app_config(app_config)
    write_json(
        evidence,
            {
                "app": {"name": "FreeMail", "version": "0.1.0-dev", "apiBaseUrl": "https://freemail.kuzuryu.ai"},
                "nativeBuilds": {"ios": "1", "android": "1"},
                "builds": {
                    "ios": {
                        "identifier": "technology.cyint.freemail",
                        "nativeBuildId": "1",
                        "signed": False,
                        "artifact": {},
                    },
                    "android": {
                        "identifier": "technology.cyint.freemail",
                        "nativeBuildId": "1",
                        "signed": False,
                        "artifact": {},
                    },
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
        "ios-device-validation",
        "android-device-validation",
        "ios-store-submission",
        "android-store-submission",
    ]
    assert [action["id"] for action in result["nextActions"]] == [
        "record-ios-signed-build",
        "record-android-signed-build",
        "record-ios-device-validation",
        "record-android-device-validation",
        "record-ios-store-submission",
        "record-android-store-submission",
    ]
    assert set(result["nextActions"][0]["failedRequirements"]) >= {
        "signed",
        "artifact-sha256",
        "artifact-bytes",
        "build-url",
    }
    assert "<https-build-evidence-url>" in result["nextActions"][0]["command"]
    assert result["evidenceDetails"]["sha256"]


def test_mobile_release_status_accepts_complete_store_submission_packet(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release-evidence.json"
    write_app_config(app_config)
    write_json(evidence, complete_evidence())

    result = summarize_mobile_release_evidence(evidence=evidence, app_config=app_config, require_store_submission=True)

    assert result["ready"] is True
    assert result["failedChecks"] == []
    assert result["nextActions"] == []
    assert [check["status"] for check in result["checks"]] == ["pass"] * 9


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
    assert [action["id"] for action in payload["nextActions"]] == [
        "record-ios-store-submission",
        "record-android-store-submission",
    ]


def test_mobile_release_status_script_discovers_domain_specific_default_evidence(tmp_path):
    app_config = tmp_path / "apps" / "mobile" / "app.json"
    evidence = tmp_path / ".freemail-qa" / "mobile-release-evidence.freemail.kuzuryu.ai.json"
    app_config.parent.mkdir(parents=True)
    evidence.parent.mkdir(parents=True)
    write_app_config(app_config)
    write_json(evidence, complete_evidence())

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "mobile_release_status.py"),
            "--require-store-submission",
        ],
        cwd=tmp_path,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert Path(payload["evidence"]).parts == (
        ".freemail-qa",
        "mobile-release-evidence.freemail.kuzuryu.ai.json",
    )


def write_app_config(path):
    write_json(
        path,
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


def complete_evidence():
    return {
        "app": {"name": "FreeMail", "version": "0.1.0-dev", "apiBaseUrl": "https://freemail.kuzuryu.ai"},
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
        "deviceValidation": {
            "ios": valid_device_validation("ios"),
            "android": valid_device_validation("android"),
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
        "privateBetaBoundary": {
            "hostname": "freemail.kuzuryu.ai",
            "vpnOnly": True,
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        },
    }


def valid_device_validation(platform):
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


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
