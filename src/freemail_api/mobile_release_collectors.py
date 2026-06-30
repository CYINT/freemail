from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .mobile_release_gate import EXPECTED_ANDROID_PACKAGE, EXPECTED_IOS_BUNDLE_ID


ALLOWED_PLATFORMS = {"ios", "android"}
ALLOWED_DISTRIBUTIONS = {"internal", "private-beta", "store-review", "production"}
ALLOWED_STORE_TRACKS = {"internal", "testflight", "private-beta", "closed-testing", "internal-testing", "store-review"}
SENSITIVE_VALUE_MARKERS = (
    "authorization:",
    "bearer ",
    "password",
    "private key",
    "secret",
    "token",
    "keystore",
    "provisioning",
)


@dataclass(frozen=True)
class MobileBuildEvidenceOptions:
    evidence: Path
    platform: str
    signed: bool
    build_url: str
    artifact_type: str
    artifact_bytes: int
    artifact_sha256: str
    distribution: str = "private-beta"


@dataclass(frozen=True)
class MobileStoreSubmissionOptions:
    evidence: Path
    platform: str
    submitted: bool
    submission_url: str
    submitted_at: datetime | None
    review_state: str
    track: str


def collect_mobile_build_evidence(options: MobileBuildEvidenceOptions) -> dict[str, Any]:
    platform = _normalize_platform(options.platform)
    payload = _load_json(options.evidence)
    artifact_type = options.artifact_type.strip().lower()
    expected_types = {"ipa"} if platform == "ios" else {"aab", "apk"}
    if artifact_type not in expected_types:
        raise ValueError(f"{platform} artifact_type must be one of: {', '.join(sorted(expected_types))}")
    if options.distribution not in ALLOWED_DISTRIBUTIONS:
        raise ValueError(f"distribution must be one of: {', '.join(sorted(ALLOWED_DISTRIBUTIONS))}")
    build = {
        "identifier": _expected_identifier(platform),
        "signed": options.signed,
        "distribution": options.distribution,
        "buildUrl": _require_https_url(options.build_url, "build_url"),
        "artifact": {
            "type": artifact_type,
            "bytes": _require_positive_int(options.artifact_bytes, "artifact_bytes"),
            "sha256": _require_sha256(options.artifact_sha256),
        },
    }
    _reject_sensitive_values(build)
    builds = payload.setdefault("builds", {})
    if not isinstance(builds, dict):
        raise ValueError("mobile evidence builds must be a JSON object")
    builds[platform] = build
    _write_json(options.evidence, payload)
    return {
        "platformReady": _build_ready(build, platform),
        "evidence": str(options.evidence),
        "platform": platform,
        "build": build,
    }


def collect_mobile_store_submission(options: MobileStoreSubmissionOptions) -> dict[str, Any]:
    platform = _normalize_platform(options.platform)
    track = options.track.strip().lower()
    if track not in ALLOWED_STORE_TRACKS:
        raise ValueError(f"track must be one of: {', '.join(sorted(ALLOWED_STORE_TRACKS))}")
    submission = {
        "store": "app-store-connect" if platform == "ios" else "play-console",
        "identifier": _expected_identifier(platform),
        "track": track,
        "submitted": options.submitted,
        "submissionUrl": _require_https_url(options.submission_url, "submission_url"),
        "submittedAt": _format_timestamp(options.submitted_at or datetime.now(timezone.utc)),
        "reviewState": _require_nonempty(options.review_state, "review_state"),
    }
    _reject_sensitive_values(submission)
    payload = _load_json(options.evidence)
    submissions = payload.setdefault("storeSubmissions", {})
    if not isinstance(submissions, dict):
        raise ValueError("mobile evidence storeSubmissions must be a JSON object")
    submissions[platform] = submission
    _write_json(options.evidence, payload)
    return {
        "platformReady": _submission_ready(submission, platform),
        "evidence": str(options.evidence),
        "platform": platform,
        "storeSubmission": submission,
    }


def _build_ready(build: dict[str, Any], platform: str) -> bool:
    artifact = build.get("artifact") if isinstance(build.get("artifact"), dict) else {}
    return (
        build.get("identifier") == _expected_identifier(platform)
        and build.get("signed") is True
        and build.get("distribution") in ALLOWED_DISTRIBUTIONS
        and _is_https_url(build.get("buildUrl"))
        and artifact.get("type") in ({"ipa"} if platform == "ios" else {"aab", "apk"})
        and _is_sha256(artifact.get("sha256"))
        and int(artifact.get("bytes", 0) or 0) > 0
    )


def _submission_ready(submission: dict[str, Any], platform: str) -> bool:
    return (
        submission.get("store") == ("app-store-connect" if platform == "ios" else "play-console")
        and submission.get("identifier") == _expected_identifier(platform)
        and submission.get("track") in ALLOWED_STORE_TRACKS
        and submission.get("submitted") is True
        and _is_https_url(submission.get("submissionUrl"))
        and _is_timezone_aware_iso8601(submission.get("submittedAt"))
        and bool(str(submission.get("reviewState", "")).strip())
    )


def _normalize_platform(value: str) -> str:
    platform = value.strip().lower()
    if platform not in ALLOWED_PLATFORMS:
        raise ValueError("platform must be ios or android")
    return platform


def _expected_identifier(platform: str) -> str:
    return EXPECTED_IOS_BUNDLE_ID if platform == "ios" else EXPECTED_ANDROID_PACKAGE


def _require_https_url(value: str, field: str) -> str:
    normalized = value.strip()
    if not _is_https_url(normalized):
        raise ValueError(f"{field} must be an HTTPS URL")
    return normalized


def _require_positive_int(value: int, field: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a positive integer") from error
    if normalized <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return normalized


def _require_nonempty(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _require_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if not _is_sha256(normalized):
        raise ValueError("artifact_sha256 must be a 64-character SHA-256 hex string")
    return normalized


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("submitted_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_https_url(value: object) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_sha256(value: object) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


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
        raise ValueError("mobile release evidence must not contain credential markers")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
