from datetime import UTC, datetime
import json
import subprocess
import sys

import pytest

from freemail_api.mobile_device_validation import (
    MobileDeviceValidationOptions,
    REQUIRED_DEVICE_CHECKS,
    collect_mobile_device_validation,
)
from freemail_api.mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate


def test_collect_mobile_device_validation_updates_platform_record(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    app_config = tmp_path / "app.json"
    write_json(app_config, valid_app_config())
    write_json(evidence, mobile_evidence_with_signed_builds())

    result = collect_mobile_device_validation(
        MobileDeviceValidationOptions(
            evidence=evidence,
            platform="IOS",
            tester="release operator",
            device_model="iPhone 15",
            os_version="iOS 18",
            evidence_url="https://example.invalid/ios-device-validation",
            tested=True,
            tested_at=datetime(2026, 6, 30, tzinfo=UTC),
            passed_checks=REQUIRED_DEVICE_CHECKS,
        )
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))

    assert result["platformReady"] is True
    assert payload["deviceValidation"]["ios"]["testedAt"] == "2026-06-30T00:00:00Z"
    assert payload["deviceValidation"]["ios"]["appVersion"] == "0.1.0-dev"
    assert [check["status"] for check in payload["deviceValidation"]["ios"]["checks"]] == ["pass"] * len(
        REQUIRED_DEVICE_CHECKS
    )

    gate = run_mobile_release_gate(MobileReleaseGateOptions(evidence=evidence, app_config=app_config))
    failed = [check["name"] for check in gate["checks"] if check["status"] != "pass"]
    assert gate["passed"] is False
    assert failed == ["android-device-validation"]


def test_collect_mobile_device_validation_stays_failing_without_explicit_tested_flag(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_signed_builds())

    result = collect_mobile_device_validation(
        MobileDeviceValidationOptions(
            evidence=evidence,
            platform="android",
            tester="release operator",
            device_model="Pixel 8",
            os_version="Android 15",
            evidence_url="https://example.invalid/android-device-validation",
            tested=False,
            tested_at=datetime(2026, 6, 30, tzinfo=UTC),
            passed_checks=REQUIRED_DEVICE_CHECKS,
        )
    )

    assert result["platformReady"] is False
    assert result["deviceValidation"]["tested"] is False


def test_collect_mobile_device_validation_rejects_timezone_free_timestamp(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_signed_builds())

    with pytest.raises(ValueError):
        collect_mobile_device_validation(
            MobileDeviceValidationOptions(
                evidence=evidence,
                platform="ios",
                tester="release operator",
                device_model="iPhone 15",
                os_version="iOS 18",
                evidence_url="https://example.invalid/ios-device-validation",
                tested=True,
                tested_at=datetime(2026, 6, 30),
                passed_checks=REQUIRED_DEVICE_CHECKS,
            )
        )


def test_collect_mobile_device_validation_rejects_credential_markers(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_signed_builds())

    with pytest.raises(ValueError):
        collect_mobile_device_validation(
            MobileDeviceValidationOptions(
                evidence=evidence,
                platform="ios",
                tester="release operator",
                device_model="iPhone 15",
                os_version="iOS 18",
                evidence_url="https://example.invalid/ios-device-validation?token=abc",
                tested=True,
                tested_at=datetime(2026, 6, 30, tzinfo=UTC),
                passed_checks=REQUIRED_DEVICE_CHECKS,
            )
        )


def test_collect_mobile_device_validation_script_exits_success_for_ready_platform(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_signed_builds())

    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_mobile_device_validation.py",
            "--evidence",
            str(evidence),
            "--platform",
            "ios",
            "--tester",
            "release operator",
            "--device-model",
            "iPhone 15",
            "--os-version",
            "iOS 18",
            "--evidence-url",
            "https://example.invalid/ios-device-validation",
            "--tested",
            "--tested-at",
            "2026-06-30T00:00:00Z",
            "--all-checks-passed",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["platformReady"] is True


def test_collect_mobile_device_validation_script_exits_nonzero_for_partial_record(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_signed_builds())

    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_mobile_device_validation.py",
            "--evidence",
            str(evidence),
            "--platform",
            "android",
            "--tester",
            "release operator",
            "--device-model",
            "Pixel 8",
            "--os-version",
            "Android 15",
            "--evidence-url",
            "https://example.invalid/android-device-validation",
            "--passed-check",
            "vpn-dns-resolution",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["platformReady"] is False
    assert payload["deviceValidation"]["checks"][0] == {"name": "vpn-dns-resolution", "status": "pass"}
    assert payload["deviceValidation"]["checks"][1] == {"name": "auth-login", "status": "pending"}


def mobile_evidence_with_signed_builds():
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
        "deviceValidation": {
            "ios": pending_device_validation("ios"),
            "android": pending_device_validation("android"),
        },
        "privateBetaBoundary": {
            "hostname": "freemail.kuzuryu.ai",
            "vpnOnly": True,
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        },
    }


def pending_device_validation(platform):
    return {
        "platform": platform,
        "tested": False,
        "testedAt": "",
        "tester": "",
        "deviceModel": "",
        "osVersion": "",
        "appVersion": "",
        "hostname": "freemail.kuzuryu.ai",
        "networkBoundary": "Dragonscale/VPN clients only",
        "evidenceUrl": "",
        "checks": [{"name": name, "status": "pending"} for name in REQUIRED_DEVICE_CHECKS],
    }


def valid_app_config():
    return {
        "expo": {
            "name": "FreeMail",
            "version": "0.1.0-dev",
            "scheme": "freemail",
            "ios": {
                "bundleIdentifier": "technology.cyint.freemail",
                "associatedDomains": ["applinks:freemail.kuzuryu.ai"],
            },
            "android": {
                "package": "technology.cyint.freemail",
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


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
