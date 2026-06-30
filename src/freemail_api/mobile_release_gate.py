from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .release_gate import _file_evidence_details


EXPECTED_IOS_BUNDLE_ID = "technology.cyint.freemail"
EXPECTED_ANDROID_PACKAGE = "technology.cyint.freemail"
EXPECTED_API_BASE_URL = "https://freemail.kuzuryu.ai"
FORBIDDEN_EVIDENCE_KEYS = {
    "apiKey",
    "api_key",
    "appleCertificate",
    "apple_certificate",
    "certificate",
    "keystore",
    "password",
    "privateKey",
    "private_key",
    "provisioningProfile",
    "provisioning_profile",
    "secret",
    "serviceAccountJson",
    "service_account_json",
    "token",
}


@dataclass(frozen=True)
class MobileReleaseGateOptions:
    evidence: Path
    app_config: Path = Path("apps/mobile/app.json")
    require_store_submission: bool = False


def run_mobile_release_gate(options: MobileReleaseGateOptions) -> dict[str, Any]:
    evidence = _load_json(options.evidence)
    app_config = _load_json(options.app_config).get("expo", {})
    checks = [
        _check_no_sensitive_keys(evidence),
        _check_app_metadata(app_config, evidence),
        _check_platform_build(evidence, platform="ios"),
        _check_platform_build(evidence, platform="android"),
        _check_private_beta_boundary(evidence),
    ]
    if options.require_store_submission:
        checks.extend(
            [
                _check_store_submission(evidence, platform="ios"),
                _check_store_submission(evidence, platform="android"),
            ]
        )
    passed = all(check["status"] == "pass" for check in checks)
    return {
        "passed": passed,
        "evidence": str(options.evidence),
        "evidenceDetails": _file_evidence_details(options.evidence),
        "checks": checks,
    }


def assert_mobile_release_gate(options: MobileReleaseGateOptions) -> dict[str, Any]:
    result = run_mobile_release_gate(options)
    if not result["passed"]:
        failed = ", ".join(check["name"] for check in result["checks"] if check["status"] != "pass")
        raise ValueError(f"mobile release gate failed: {failed}")
    return result


def _check_no_sensitive_keys(evidence: dict[str, Any]) -> dict[str, Any]:
    found = sorted(_find_forbidden_keys(evidence))
    return _check("no-signing-secrets", not found, {"forbiddenKeys": found})


def _find_forbidden_keys(value: Any, prefix: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            if str(key) in FORBIDDEN_EVIDENCE_KEYS:
                found.add(key_path)
            found.update(_find_forbidden_keys(child, key_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.update(_find_forbidden_keys(child, f"{prefix}[{index}]"))
    return found


def _check_app_metadata(app_config: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    app = evidence.get("app", {})
    passed = (
        app_config.get("name") == "FreeMail"
        and app_config.get("ios", {}).get("bundleIdentifier") == EXPECTED_IOS_BUNDLE_ID
        and app_config.get("android", {}).get("package") == EXPECTED_ANDROID_PACKAGE
        and app_config.get("extra", {}).get("apiBaseUrl") == EXPECTED_API_BASE_URL
        and app.get("name") == app_config.get("name")
        and app.get("version") == app_config.get("version")
        and app.get("apiBaseUrl") == EXPECTED_API_BASE_URL
    )
    return _check(
        "app-metadata",
        passed,
        {
            "name": app.get("name"),
            "version": app.get("version"),
            "apiBaseUrl": app.get("apiBaseUrl"),
            "iosBundleIdentifier": app_config.get("ios", {}).get("bundleIdentifier"),
            "androidPackage": app_config.get("android", {}).get("package"),
        },
    )


def _check_platform_build(evidence: dict[str, Any], *, platform: str) -> dict[str, Any]:
    build = evidence.get("builds", {}).get(platform, {})
    expected_identifier = EXPECTED_IOS_BUNDLE_ID if platform == "ios" else EXPECTED_ANDROID_PACKAGE
    expected_artifact_types = {"ipa"} if platform == "ios" else {"aab", "apk"}
    artifact = build.get("artifact", {})
    passed = (
        build.get("signed") is True
        and build.get("identifier") == expected_identifier
        and build.get("distribution") in {"internal", "private-beta", "store-review", "production"}
        and artifact.get("type") in expected_artifact_types
        and _is_sha256(artifact.get("sha256"))
        and int(artifact.get("bytes", 0) or 0) > 0
        and bool(str(build.get("buildUrl", "")).strip())
    )
    return _check(
        f"{platform}-signed-build",
        passed,
        {
            "identifier": build.get("identifier"),
            "signed": build.get("signed"),
            "distribution": build.get("distribution"),
            "artifactType": artifact.get("type"),
            "artifactBytes": artifact.get("bytes"),
            "artifactSha256": artifact.get("sha256"),
            "buildUrl": build.get("buildUrl"),
        },
    )


def _check_private_beta_boundary(evidence: dict[str, Any]) -> dict[str, Any]:
    boundary = evidence.get("privateBetaBoundary", {})
    passed = (
        boundary.get("vpnOnly") is True
        and boundary.get("publicInternet") is False
        and str(boundary.get("hostname", "")).lower() == "freemail.kuzuryu.ai"
        and "vpn" in str(boundary.get("requiredBoundary", "")).lower()
    )
    return _check(
        "private-beta-boundary",
        passed,
        {
            "hostname": boundary.get("hostname"),
            "vpnOnly": boundary.get("vpnOnly"),
            "publicInternet": boundary.get("publicInternet"),
            "requiredBoundary": boundary.get("requiredBoundary"),
        },
    )


def _check_store_submission(evidence: dict[str, Any], *, platform: str) -> dict[str, Any]:
    submission = evidence.get("storeSubmissions", {}).get(platform, {})
    expected_store = "app-store-connect" if platform == "ios" else "play-console"
    expected_identifier = EXPECTED_IOS_BUNDLE_ID if platform == "ios" else EXPECTED_ANDROID_PACKAGE
    allowed_tracks = {"internal", "testflight", "private-beta", "closed-testing", "internal-testing", "store-review"}
    passed = (
        submission.get("store") == expected_store
        and submission.get("identifier") == expected_identifier
        and submission.get("track") in allowed_tracks
        and submission.get("submitted") is True
        and bool(str(submission.get("submissionUrl", "")).strip())
        and bool(str(submission.get("submittedAt", "")).strip())
        and bool(str(submission.get("reviewState", "")).strip())
    )
    return _check(
        f"{platform}-store-submission",
        passed,
        {
            "store": submission.get("store"),
            "identifier": submission.get("identifier"),
            "track": submission.get("track"),
            "submitted": submission.get("submitted"),
            "submissionUrl": submission.get("submissionUrl"),
            "submittedAt": submission.get("submittedAt"),
            "reviewState": submission.get("reviewState"),
        },
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _is_sha256(value: object) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "details": details}
