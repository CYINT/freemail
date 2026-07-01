from datetime import UTC, datetime
import json
import subprocess
import sys

import pytest

from freemail_api.mobile_release_collectors import (
    MobileBuildEvidenceOptions,
    MobileStoreSubmissionOptions,
    collect_mobile_build_evidence,
    collect_mobile_store_submission,
)
from freemail_api.mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate


def test_collect_mobile_build_evidence_updates_platform_record(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    app_config = tmp_path / "app.json"
    write_json(app_config, valid_app_config())
    write_json(evidence, mobile_evidence_with_device_validation())

    result = collect_mobile_build_evidence(
        MobileBuildEvidenceOptions(
            evidence=evidence,
            platform="ios",
            signed=True,
            build_url="https://example.invalid/ios-build",
            artifact_type="ipa",
            artifact_bytes=123,
            artifact_sha256="a" * 64,
        )
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))

    assert result["platformReady"] is True
    assert payload["builds"]["ios"]["signed"] is True
    assert payload["builds"]["ios"]["artifact"]["sha256"] == "a" * 64

    gate = run_mobile_release_gate(MobileReleaseGateOptions(evidence=evidence, app_config=app_config))
    failed = [check["name"] for check in gate["checks"] if check["status"] != "pass"]
    assert gate["passed"] is False
    assert failed == ["android-signed-build"]


def test_collect_mobile_build_evidence_stays_failing_without_signed_flag(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_device_validation())

    result = collect_mobile_build_evidence(
        MobileBuildEvidenceOptions(
            evidence=evidence,
            platform="android",
            signed=False,
            build_url="https://example.invalid/android-build",
            artifact_type="aab",
            artifact_bytes=456,
            artifact_sha256="b" * 64,
        )
    )

    assert result["platformReady"] is False
    assert result["build"]["signed"] is False


def test_collect_mobile_build_evidence_rejects_wrong_artifact_type(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_device_validation())

    with pytest.raises(ValueError):
        collect_mobile_build_evidence(
            MobileBuildEvidenceOptions(
                evidence=evidence,
                platform="ios",
                signed=True,
                build_url="https://example.invalid/ios-build",
                artifact_type="aab",
                artifact_bytes=123,
                artifact_sha256="a" * 64,
            )
        )


def test_collect_mobile_store_submission_updates_platform_record(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_device_validation())

    result = collect_mobile_store_submission(
        MobileStoreSubmissionOptions(
            evidence=evidence,
            platform="android",
            submitted=True,
            track="internal-testing",
            submission_url="https://example.invalid/play-internal",
            submitted_at=datetime(2026, 6, 30, tzinfo=UTC),
            review_state="draft-release-created",
        )
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))

    assert result["platformReady"] is True
    assert payload["storeSubmissions"]["android"]["store"] == "play-console"
    assert payload["storeSubmissions"]["android"]["submittedAt"] == "2026-06-30T00:00:00Z"


def test_collect_mobile_store_submission_stays_failing_without_submitted_flag(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_device_validation())

    result = collect_mobile_store_submission(
        MobileStoreSubmissionOptions(
            evidence=evidence,
            platform="ios",
            submitted=False,
            track="testflight",
            submission_url="https://example.invalid/testflight",
            submitted_at=datetime(2026, 6, 30, tzinfo=UTC),
            review_state="processing",
        )
    )

    assert result["platformReady"] is False
    assert result["storeSubmission"]["submitted"] is False


def test_collect_mobile_store_submission_rejects_timezone_free_timestamp(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_device_validation())

    with pytest.raises(ValueError):
        collect_mobile_store_submission(
            MobileStoreSubmissionOptions(
                evidence=evidence,
                platform="ios",
                submitted=True,
                track="testflight",
                submission_url="https://example.invalid/testflight",
                submitted_at=datetime(2026, 6, 30),
                review_state="processing",
            )
        )


def test_collectors_reject_credential_markers(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_device_validation())

    with pytest.raises(ValueError):
        collect_mobile_store_submission(
            MobileStoreSubmissionOptions(
                evidence=evidence,
                platform="android",
                submitted=True,
                track="internal-testing",
                submission_url="https://example.invalid/play?token=abc",
                submitted_at=datetime(2026, 6, 30, tzinfo=UTC),
                review_state="draft-release-created",
            )
        )


def test_collect_mobile_build_evidence_script_exits_success_for_ready_platform(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_device_validation())

    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_mobile_build_evidence.py",
            "--evidence",
            str(evidence),
            "--platform",
            "ios",
            "--signed",
            "--build-url",
            "https://example.invalid/ios-build",
            "--artifact-type",
            "ipa",
            "--artifact-bytes",
            "123",
            "--artifact-sha256",
            "a" * 64,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["platformReady"] is True


def test_collect_mobile_store_submission_script_exits_nonzero_without_submitted_flag(tmp_path):
    evidence = tmp_path / "mobile-release-evidence.json"
    write_json(evidence, mobile_evidence_with_device_validation())

    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_mobile_store_submission.py",
            "--evidence",
            str(evidence),
            "--platform",
            "ios",
            "--track",
            "testflight",
            "--submission-url",
            "https://example.invalid/testflight",
            "--submitted-at",
            "2026-06-30T00:00:00Z",
            "--review-state",
            "processing",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["platformReady"] is False


def mobile_evidence_with_device_validation():
    return {
        "app": {"name": "FreeMail", "version": "0.1.0-dev", "apiBaseUrl": "https://freemail.kuzuryu.ai"},
        "builds": {
            "ios": {"identifier": "technology.cyint.freemail", "signed": False, "artifact": {"type": "ipa"}},
            "android": {"identifier": "technology.cyint.freemail", "signed": False, "artifact": {"type": "aab"}},
        },
        "deviceValidation": {
            "ios": valid_device_validation("ios"),
            "android": valid_device_validation("android"),
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
            {"name": "offline-cache", "status": "pass"},
        ],
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
