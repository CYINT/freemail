import json
import hashlib

from freemail_api.mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate


def test_mobile_release_gate_accepts_signed_build_evidence(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release.json"
    write_json(
        app_config,
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
    write_json(evidence, valid_evidence())

    result = run_mobile_release_gate(MobileReleaseGateOptions(evidence=evidence, app_config=app_config))

    assert result["passed"] is True
    assert result["evidenceDetails"]["sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()


def test_mobile_release_gate_accepts_store_submission_evidence_when_required(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release.json"
    write_json(
        app_config,
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
    payload = valid_evidence()
    payload["storeSubmissions"] = valid_store_submissions()
    write_json(evidence, payload)

    result = run_mobile_release_gate(
        MobileReleaseGateOptions(evidence=evidence, app_config=app_config, require_store_submission=True)
    )

    assert result["passed"] is True
    assert result["checks"][-2]["name"] == "ios-store-submission"
    assert result["checks"][-1]["name"] == "android-store-submission"


def test_mobile_release_gate_requires_store_submission_evidence_when_enabled(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release.json"
    write_json(
        app_config,
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
    write_json(evidence, valid_evidence())

    result = run_mobile_release_gate(
        MobileReleaseGateOptions(evidence=evidence, app_config=app_config, require_store_submission=True)
    )

    assert result["passed"] is False
    assert result["checks"][-2]["name"] == "ios-store-submission"
    assert result["checks"][-2]["status"] == "fail"
    assert result["checks"][-1]["name"] == "android-store-submission"
    assert result["checks"][-1]["status"] == "fail"


def test_mobile_release_gate_rejects_secret_bearing_evidence(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release.json"
    write_json(
        app_config,
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
    payload = valid_evidence()
    payload["builds"]["ios"]["privateKey"] = "do-not-store"
    write_json(evidence, payload)

    result = run_mobile_release_gate(MobileReleaseGateOptions(evidence=evidence, app_config=app_config))

    assert result["passed"] is False
    assert result["checks"][0]["name"] == "no-signing-secrets"
    assert result["checks"][0]["details"]["forbiddenKeys"] == ["builds.ios.privateKey"]


def test_mobile_release_gate_rejects_wrong_android_identifier(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release.json"
    write_json(
        app_config,
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
    payload = valid_evidence()
    payload["builds"]["android"]["identifier"] = "com.example.wrong"
    write_json(evidence, payload)

    result = run_mobile_release_gate(MobileReleaseGateOptions(evidence=evidence, app_config=app_config))

    assert result["passed"] is False
    android_check = next(check for check in result["checks"] if check["name"] == "android-signed-build")
    assert android_check["status"] == "fail"


def test_mobile_release_gate_rejects_malformed_artifact_hash(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release.json"
    write_json(
        app_config,
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
    payload = valid_evidence()
    payload["builds"]["ios"]["artifact"]["sha256"] = "abc"
    write_json(evidence, payload)

    result = run_mobile_release_gate(MobileReleaseGateOptions(evidence=evidence, app_config=app_config))

    assert result["passed"] is False
    ios_check = next(check for check in result["checks"] if check["name"] == "ios-signed-build")
    assert ios_check["status"] == "fail"


def test_mobile_release_gate_rejects_insecure_build_url(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release.json"
    write_json(
        app_config,
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
    payload = valid_evidence()
    payload["builds"]["android"]["buildUrl"] = "http://example.invalid/android-build"
    write_json(evidence, payload)

    result = run_mobile_release_gate(MobileReleaseGateOptions(evidence=evidence, app_config=app_config))

    assert result["passed"] is False
    android_check = next(check for check in result["checks"] if check["name"] == "android-signed-build")
    assert android_check["status"] == "fail"


def test_mobile_release_gate_rejects_insecure_store_submission_url(tmp_path):
    app_config = tmp_path / "app.json"
    evidence = tmp_path / "mobile-release.json"
    write_json(
        app_config,
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
    payload = valid_evidence()
    payload["storeSubmissions"] = valid_store_submissions()
    payload["storeSubmissions"]["ios"]["submissionUrl"] = "http://example.invalid/testflight"
    write_json(evidence, payload)

    result = run_mobile_release_gate(
        MobileReleaseGateOptions(evidence=evidence, app_config=app_config, require_store_submission=True)
    )

    assert result["passed"] is False
    ios_check = next(check for check in result["checks"] if check["name"] == "ios-store-submission")
    assert ios_check["status"] == "fail"


def valid_evidence():
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
        "privateBetaBoundary": {
            "hostname": "freemail.kuzuryu.ai",
            "vpnOnly": True,
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        },
    }


def valid_store_submissions():
    return {
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
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
