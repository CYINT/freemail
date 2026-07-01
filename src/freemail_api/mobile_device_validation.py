from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REQUIRED_DEVICE_CHECKS = (
    "vpn-dns-resolution",
    "auth-login",
    "inbox-sync",
    "message-read",
    "compose-send",
    "invite-link-open",
    "offline-cache",
)
ALLOWED_PLATFORMS = {"ios", "android"}
ALLOWED_STATUSES = {"pass", "fail", "pending"}
SENSITIVE_VALUE_MARKERS = (
    "authorization:",
    "bearer ",
    "password",
    "private key",
    "secret",
    "token",
)


@dataclass(frozen=True)
class MobileDeviceValidationOptions:
    evidence: Path
    platform: str
    tester: str
    device_model: str
    os_version: str
    evidence_url: str
    tested: bool = False
    tested_at: datetime | None = None
    app_version: str | None = None
    hostname: str = "freemail.kuzuryu.ai"
    network_boundary: str = "Dragonscale/VPN clients only"
    passed_checks: tuple[str, ...] = ()
    failed_checks: tuple[str, ...] = ()


def collect_mobile_device_validation(options: MobileDeviceValidationOptions) -> dict[str, Any]:
    platform = _normalize_platform(options.platform)
    payload = _load_json(options.evidence)
    app = payload.get("app") if isinstance(payload.get("app"), dict) else {}
    app_version = options.app_version or str(app.get("version", "")).strip()
    validation = _build_validation_payload(options, platform, app_version)
    _reject_sensitive_values(validation)

    device_validation = payload.setdefault("deviceValidation", {})
    if not isinstance(device_validation, dict):
        raise ValueError("mobile evidence deviceValidation must be a JSON object")
    device_validation[platform] = validation
    _write_json(options.evidence, payload)

    return {
        "platformReady": _platform_ready(validation, app_version),
        "evidence": str(options.evidence),
        "platform": platform,
        "deviceValidation": validation,
    }


def _build_validation_payload(
    options: MobileDeviceValidationOptions,
    platform: str,
    app_version: str,
) -> dict[str, Any]:
    if not _is_https_url(options.evidence_url):
        raise ValueError("evidence_url must be an HTTPS URL")
    for label, value in {
        "tester": options.tester,
        "device_model": options.device_model,
        "os_version": options.os_version,
        "app_version": app_version,
        "hostname": options.hostname,
        "network_boundary": options.network_boundary,
    }.items():
        if not str(value or "").strip():
            raise ValueError(f"{label} is required")

    tested_at = _format_timestamp(options.tested_at or datetime.now(timezone.utc))
    statuses = _device_check_statuses(options.passed_checks, options.failed_checks)
    return {
        "platform": platform,
        "tested": options.tested,
        "testedAt": tested_at,
        "tester": options.tester.strip(),
        "deviceModel": options.device_model.strip(),
        "osVersion": options.os_version.strip(),
        "appVersion": app_version,
        "hostname": options.hostname.strip().lower().rstrip("."),
        "networkBoundary": options.network_boundary.strip(),
        "evidenceUrl": options.evidence_url.strip(),
        "checks": [{"name": name, "status": status} for name, status in statuses.items()],
    }


def _device_check_statuses(passed_checks: tuple[str, ...], failed_checks: tuple[str, ...]) -> dict[str, str]:
    passed = {_normalize_check_name(name) for name in passed_checks}
    failed = {_normalize_check_name(name) for name in failed_checks}
    overlap = passed.intersection(failed)
    if overlap:
        raise ValueError(f"device checks cannot be both pass and fail: {', '.join(sorted(overlap))}")
    unknown = sorted(passed.union(failed).difference(REQUIRED_DEVICE_CHECKS))
    if unknown:
        raise ValueError(f"unknown device checks: {', '.join(unknown)}")
    return {
        name: "pass" if name in passed else "fail" if name in failed else "pending"
        for name in REQUIRED_DEVICE_CHECKS
    }


def _platform_ready(validation: dict[str, Any], app_version: str) -> bool:
    checks = validation.get("checks")
    return (
        validation.get("tested") is True
        and validation.get("appVersion") == app_version
        and validation.get("hostname") == "freemail.kuzuryu.ai"
        and "vpn" in str(validation.get("networkBoundary", "")).lower()
        and isinstance(checks, list)
        and all(
            isinstance(check, dict)
            and check.get("name") in REQUIRED_DEVICE_CHECKS
            and check.get("status") == "pass"
            for check in checks
        )
        and len(checks) == len(REQUIRED_DEVICE_CHECKS)
    )


def _normalize_platform(value: str) -> str:
    platform = value.strip().lower()
    if platform not in ALLOWED_PLATFORMS:
        raise ValueError("platform must be ios or android")
    return platform


def _normalize_check_name(value: str) -> str:
    return value.strip().lower()


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("tested_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_https_url(value: object) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def _reject_sensitive_values(value: object) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _reject_sensitive_values(child)
        return
    if isinstance(value, list):
        for child in value:
            _reject_sensitive_values(child)
        return
    if not isinstance(value, str):
        return
    lowered = value.lower()
    if any(marker in lowered for marker in SENSITIVE_VALUE_MARKERS):
        raise ValueError("mobile device validation evidence must not contain credential markers")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
