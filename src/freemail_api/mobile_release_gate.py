from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .release_gate import _file_evidence_details


EXPECTED_IOS_BUNDLE_ID = "technology.cyint.freemail"
EXPECTED_ANDROID_PACKAGE = "technology.cyint.freemail"
EXPECTED_API_BASE_URL = "https://freemail.kuzuryu.ai"
EXPECTED_URL_SCHEME = "freemail"
EXPECTED_ASSOCIATED_DOMAIN = "applinks:freemail.kuzuryu.ai"
EXPECTED_INVITE_HOST = "freemail.kuzuryu.ai"
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
        _check_device_validation(evidence, app_config, platform="ios"),
        _check_device_validation(evidence, app_config, platform="android"),
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
    native_builds = evidence.get("nativeBuilds", {}) if isinstance(evidence.get("nativeBuilds"), dict) else {}
    ios_build_number = str(app_config.get("ios", {}).get("buildNumber", "")).strip()
    android_version_code = str(app_config.get("android", {}).get("versionCode", "")).strip()
    requirements = {
        "app-config-name": app_config.get("name") == "FreeMail",
        "app-config-scheme": app_config.get("scheme") == EXPECTED_URL_SCHEME,
        "app-config-ios-bundle": app_config.get("ios", {}).get("bundleIdentifier") == EXPECTED_IOS_BUNDLE_ID,
        "app-config-ios-build-number": bool(ios_build_number),
        "app-config-ios-associated-domain": EXPECTED_ASSOCIATED_DOMAIN
        in app_config.get("ios", {}).get("associatedDomains", []),
        "app-config-android-package": app_config.get("android", {}).get("package") == EXPECTED_ANDROID_PACKAGE,
        "app-config-android-version-code": bool(android_version_code),
        "app-config-android-invite-intent-filter": _has_android_invite_intent_filter(app_config),
        "app-config-api-base-url": app_config.get("extra", {}).get("apiBaseUrl") == EXPECTED_API_BASE_URL,
        "evidence-app-name": app.get("name") == app_config.get("name"),
        "evidence-app-version": app.get("version") == app_config.get("version"),
        "evidence-api-base-url": app.get("apiBaseUrl") == EXPECTED_API_BASE_URL,
        "evidence-native-builds-ios": str(native_builds.get("ios", "")).strip() == ios_build_number,
        "evidence-native-builds-android": str(native_builds.get("android", "")).strip() == android_version_code,
    }
    failed_requirements = [name for name, passed in requirements.items() if not passed]
    return _check(
        "app-metadata",
        not failed_requirements,
        {
            "name": app.get("name"),
            "version": app.get("version"),
            "apiBaseUrl": app.get("apiBaseUrl"),
            "scheme": app_config.get("scheme"),
            "iosBundleIdentifier": app_config.get("ios", {}).get("bundleIdentifier"),
            "iosBuildNumber": ios_build_number,
            "iosAssociatedDomains": app_config.get("ios", {}).get("associatedDomains", []),
            "androidPackage": app_config.get("android", {}).get("package"),
            "androidVersionCode": android_version_code,
            "androidInviteIntentFilter": _has_android_invite_intent_filter(app_config),
            "evidenceNativeBuilds": native_builds,
            "failedRequirements": failed_requirements,
        },
    )


def _has_android_invite_intent_filter(app_config: dict[str, Any]) -> bool:
    filters = app_config.get("android", {}).get("intentFilters", [])
    if not isinstance(filters, list):
        return False
    for intent_filter in filters:
        if not isinstance(intent_filter, dict):
            continue
        categories = intent_filter.get("category", [])
        data_items = intent_filter.get("data", [])
        if (
            intent_filter.get("action") == "VIEW"
            and intent_filter.get("autoVerify") is True
            and isinstance(categories, list)
            and {"BROWSABLE", "DEFAULT"}.issubset(set(categories))
            and isinstance(data_items, list)
            and any(
                isinstance(item, dict)
                and item.get("scheme") == "https"
                and item.get("host") == EXPECTED_INVITE_HOST
                for item in data_items
            )
        ):
            return True
    return False


def _check_platform_build(evidence: dict[str, Any], *, platform: str) -> dict[str, Any]:
    build = evidence.get("builds", {}).get(platform, {})
    expected_identifier = EXPECTED_IOS_BUNDLE_ID if platform == "ios" else EXPECTED_ANDROID_PACKAGE
    expected_native_build_id = _expected_native_build_id(evidence, platform)
    expected_artifact_types = {"ipa"} if platform == "ios" else {"aab", "apk"}
    artifact = build.get("artifact", {})
    requirements = {
        "identifier": build.get("identifier") == expected_identifier,
        "native-build-id": str(build.get("nativeBuildId", "")).strip() == expected_native_build_id,
        "signed": build.get("signed") is True,
        "distribution": build.get("distribution") in {"internal", "private-beta", "store-review", "production"},
        "artifact-type": artifact.get("type") in expected_artifact_types,
        "artifact-sha256": _is_sha256(artifact.get("sha256")),
        "artifact-bytes": int(artifact.get("bytes", 0) or 0) > 0,
        "build-url": _is_https_url(build.get("buildUrl")),
    }
    failed_requirements = _failed_requirements(requirements)
    return _check(
        f"{platform}-signed-build",
        not failed_requirements,
        {
            "identifier": build.get("identifier"),
            "nativeBuildId": build.get("nativeBuildId"),
            "expectedNativeBuildId": expected_native_build_id,
            "signed": build.get("signed"),
            "distribution": build.get("distribution"),
            "artifactType": artifact.get("type"),
            "artifactBytes": artifact.get("bytes"),
            "artifactSha256": artifact.get("sha256"),
            "buildUrl": build.get("buildUrl"),
            "failedRequirements": failed_requirements,
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


def _check_device_validation(evidence: dict[str, Any], app_config: dict[str, Any], *, platform: str) -> dict[str, Any]:
    validation = evidence.get("deviceValidation", {}).get(platform, {})
    checks = validation.get("checks", [])
    check_names = [check.get("name") for check in checks if isinstance(check, dict)] if isinstance(checks, list) else []
    failed_checks = [
        check.get("name")
        for check in checks
        if isinstance(check, dict) and check.get("status") != "pass"
    ] if isinstance(checks, list) else ["checks"]
    required_checks = {
        "vpn-dns-resolution",
        "auth-login",
        "inbox-sync",
        "message-read",
        "compose-send",
        "invite-link-open",
        "offline-cache",
    }
    app = evidence.get("app", {})
    missing_checks = sorted(required_checks.difference(check_names))
    requirements = {
        "platform": validation.get("platform") == platform,
        "tested": validation.get("tested") is True,
        "tested-at": _is_timezone_aware_iso8601(validation.get("testedAt")),
        "tester": bool(str(validation.get("tester", "")).strip()),
        "device-model": bool(str(validation.get("deviceModel", "")).strip()),
        "os-version": bool(str(validation.get("osVersion", "")).strip()),
        "app-version": validation.get("appVersion") == app.get("version") == app_config.get("version"),
        "hostname": str(validation.get("hostname", "")).lower() == "freemail.kuzuryu.ai",
        "network-boundary": "vpn" in str(validation.get("networkBoundary", "")).lower(),
        "evidence-url": _is_https_url(validation.get("evidenceUrl")),
        "checks-list": isinstance(checks, list),
        "required-checks": not missing_checks,
        "passing-checks": not failed_checks,
    }
    failed_requirements = _failed_requirements(requirements)
    return _check(
        f"{platform}-device-validation",
        not failed_requirements,
        {
            "platform": validation.get("platform"),
            "tested": validation.get("tested"),
            "testedAt": validation.get("testedAt"),
            "tester": validation.get("tester"),
            "deviceModel": validation.get("deviceModel"),
            "osVersion": validation.get("osVersion"),
            "appVersion": validation.get("appVersion"),
            "hostname": validation.get("hostname"),
            "networkBoundary": validation.get("networkBoundary"),
            "evidenceUrl": validation.get("evidenceUrl"),
            "missingChecks": missing_checks,
            "failedChecks": failed_checks,
            "failedRequirements": failed_requirements,
        },
    )


def _check_store_submission(evidence: dict[str, Any], *, platform: str) -> dict[str, Any]:
    submission = evidence.get("storeSubmissions", {}).get(platform, {})
    build = evidence.get("builds", {}).get(platform, {})
    expected_store = "app-store-connect" if platform == "ios" else "play-console"
    expected_identifier = EXPECTED_IOS_BUNDLE_ID if platform == "ios" else EXPECTED_ANDROID_PACKAGE
    expected_native_build_id = _expected_native_build_id(evidence, platform)
    allowed_tracks = {"internal", "testflight", "private-beta", "closed-testing", "internal-testing", "store-review"}
    requirements = {
        "store": submission.get("store") == expected_store,
        "identifier": submission.get("identifier") == expected_identifier,
        "native-build-id": str(submission.get("nativeBuildId", "")).strip() == expected_native_build_id,
        "signed-build-native-build-id": str(submission.get("nativeBuildId", "")).strip()
        == str(build.get("nativeBuildId", "")).strip(),
        "track": submission.get("track") in allowed_tracks,
        "submitted": submission.get("submitted") is True,
        "submission-url": _is_https_url(submission.get("submissionUrl")),
        "submitted-at": _is_timezone_aware_iso8601(submission.get("submittedAt")),
        "review-state": bool(str(submission.get("reviewState", "")).strip()),
    }
    failed_requirements = _failed_requirements(requirements)
    return _check(
        f"{platform}-store-submission",
        not failed_requirements,
        {
            "store": submission.get("store"),
            "identifier": submission.get("identifier"),
            "nativeBuildId": submission.get("nativeBuildId"),
            "expectedNativeBuildId": expected_native_build_id,
            "buildNativeBuildId": build.get("nativeBuildId"),
            "track": submission.get("track"),
            "submitted": submission.get("submitted"),
            "submissionUrl": submission.get("submissionUrl"),
            "submittedAt": submission.get("submittedAt"),
            "reviewState": submission.get("reviewState"),
            "failedRequirements": failed_requirements,
        },
    )


def _expected_native_build_id(evidence: dict[str, Any], platform: str) -> str:
    native_builds = evidence.get("nativeBuilds") if isinstance(evidence.get("nativeBuilds"), dict) else {}
    value = native_builds.get(platform) if isinstance(native_builds, dict) else None
    return str(value or "").strip()


def _failed_requirements(requirements: dict[str, bool]) -> list[str]:
    return [name for name, passed in requirements.items() if not passed]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _is_sha256(value: object) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _is_https_url(value: object) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_timezone_aware_iso8601(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "details": details}
