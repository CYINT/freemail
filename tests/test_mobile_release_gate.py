import json

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
                "artifact": {"type": "ipa", "bytes": 123, "sha256": "abc"},
            },
            "android": {
                "identifier": "technology.cyint.freemail",
                "signed": True,
                "distribution": "private-beta",
                "buildUrl": "https://example.invalid/android-build",
                "artifact": {"type": "aab", "bytes": 456, "sha256": "def"},
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
