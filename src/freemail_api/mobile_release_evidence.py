from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .mobile_release_gate import EXPECTED_ANDROID_PACKAGE
from .mobile_release_gate import EXPECTED_API_BASE_URL
from .mobile_release_gate import EXPECTED_IOS_BUNDLE_ID


MOBILE_EVIDENCE_FILENAME = "mobile-release-evidence.json"
MOBILE_EVIDENCE_DOMAIN_FILENAME = "mobile-release-evidence.freemail.kuzuryu.ai.json"
DEFAULT_MOBILE_RELEASE_EVIDENCE_CANDIDATES = (
    Path(".freemail-qa") / MOBILE_EVIDENCE_DOMAIN_FILENAME,
    Path(".freemail-qa") / MOBILE_EVIDENCE_FILENAME,
)


def default_mobile_release_evidence_path() -> Path:
    return next(
        (path for path in DEFAULT_MOBILE_RELEASE_EVIDENCE_CANDIDATES if path.exists()),
        DEFAULT_MOBILE_RELEASE_EVIDENCE_CANDIDATES[0],
    )


@dataclass(frozen=True)
class MobileReleaseEvidenceTemplateOptions:
    output: Path
    app_config: Path = Path("apps/mobile/app.json")
    force: bool = False
    generated_at: datetime | None = None


def create_mobile_release_evidence_template(options: MobileReleaseEvidenceTemplateOptions) -> dict[str, Any]:
    generated_at = _format_timestamp(options.generated_at or datetime.now(timezone.utc))
    app_config = _load_app_config(options.app_config)
    payload = _mobile_release_template(app_config, generated_at)
    _write_json(options.output, payload, force=options.force)
    return {"generatedAt": generated_at, "file": str(options.output)}


def _load_app_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("expo"), dict):
        raise ValueError(f"{path} must contain an Expo app JSON object")
    expo = payload["expo"]
    return {
        "name": expo.get("name", "FreeMail"),
        "version": expo.get("version", ""),
        "apiBaseUrl": expo.get("extra", {}).get("apiBaseUrl", EXPECTED_API_BASE_URL),
        "iosBuildNumber": str(expo.get("ios", {}).get("buildNumber", "")).strip(),
        "androidVersionCode": str(expo.get("android", {}).get("versionCode", "")).strip(),
    }


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _mobile_release_template(app_config: dict[str, Any], generated_at: str) -> dict[str, Any]:
    return {
        "generatedAt": generated_at,
        "draftOnly": True,
        "app": {
            "name": app_config["name"],
            "version": app_config["version"],
            "apiBaseUrl": app_config["apiBaseUrl"],
        },
        "nativeBuilds": {
            "ios": app_config["iosBuildNumber"],
            "android": app_config["androidVersionCode"],
        },
        "builds": {
            "ios": _build_template(
                identifier=EXPECTED_IOS_BUNDLE_ID,
                artifact_type="ipa",
                native_build_id=app_config["iosBuildNumber"],
                evidence_note="Fill after the signed iOS IPA is produced in the private signing environment.",
            ),
            "android": _build_template(
                identifier=EXPECTED_ANDROID_PACKAGE,
                artifact_type="aab",
                native_build_id=app_config["androidVersionCode"],
                evidence_note="Fill after the signed Android AAB or APK is produced in the private signing environment.",
            ),
        },
        "storeSubmissions": {
            "ios": _submission_template(
                store="app-store-connect",
                identifier=EXPECTED_IOS_BUNDLE_ID,
                track="testflight",
                native_build_id=app_config["iosBuildNumber"],
                evidence_note="Fill after TestFlight or App Store Connect submission is complete.",
            ),
            "android": _submission_template(
                store="play-console",
                identifier=EXPECTED_ANDROID_PACKAGE,
                track="internal-testing",
                native_build_id=app_config["androidVersionCode"],
                evidence_note="Fill after Play Console internal-testing or closed-testing submission is complete.",
            ),
        },
        "deviceValidation": {
            "ios": _device_validation_template(
                platform="ios",
                evidence_note="Fill after a real iOS device validates the private-beta workflow over VPN.",
            ),
            "android": _device_validation_template(
                platform="android",
                evidence_note="Fill after a real Android device validates the private-beta workflow over VPN.",
            ),
        },
        "privateBetaBoundary": {
            "hostname": "freemail.kuzuryu.ai",
            "vpnOnly": True,
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        },
        "notes": [
            "Credential-free draft only; do not add signing material, passwords, service-account JSON, or raw tokens.",
            "The mobile release gate must fail until signed build, store-submission, and device-validation evidence is filled in.",
        ],
    }


def _build_template(*, identifier: str, artifact_type: str, native_build_id: str, evidence_note: str) -> dict[str, Any]:
    return {
        "identifier": identifier,
        "nativeBuildId": native_build_id,
        "signed": False,
        "distribution": "private-beta",
        "buildUrl": "",
        "artifact": {"type": artifact_type, "bytes": 0, "sha256": ""},
        "evidenceNote": evidence_note,
    }


def _submission_template(*, store: str, identifier: str, track: str, native_build_id: str, evidence_note: str) -> dict[str, Any]:
    return {
        "store": store,
        "identifier": identifier,
        "nativeBuildId": native_build_id,
        "track": track,
        "submitted": False,
        "submissionUrl": "",
        "submittedAt": "",
        "reviewState": "",
        "evidenceNote": evidence_note,
    }


def _device_validation_template(*, platform: str, evidence_note: str) -> dict[str, Any]:
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
        "checks": [
            {"name": "vpn-dns-resolution", "status": "pending"},
            {"name": "auth-login", "status": "pending"},
            {"name": "inbox-sync", "status": "pending"},
            {"name": "message-read", "status": "pending"},
            {"name": "compose-send", "status": "pending"},
            {"name": "invite-link-open", "status": "pending"},
            {"name": "offline-cache", "status": "pending"},
        ],
        "evidenceNote": evidence_note,
    }


def _write_json(path: Path, payload: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to overwrite draft template")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
