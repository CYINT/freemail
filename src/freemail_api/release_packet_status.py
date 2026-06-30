from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from .mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate
from .release_gate import _check_private_beta_evidence, _check_release_notes


@dataclass(frozen=True)
class ReleasePacketStatusOptions:
    metadata_backup: Path | None = None
    mail_store_backup: Path | None = None
    mobile_release_evidence: Path | None = None
    mobile_app_config: Path = Path("apps/mobile/app.json")
    private_beta_evidence: Path | None = None
    release_notes: Path | None = None
    release_version: str | None = None
    require_mobile_store_submission: bool = False


def summarize_release_packet(options: ReleasePacketStatusOptions) -> dict[str, Any]:
    artifacts = [
        _artifact("--metadata-backup", options.metadata_backup),
        _artifact("--mail-store-backup", options.mail_store_backup),
        _artifact("--mobile-release-evidence", options.mobile_release_evidence),
        _artifact("--mobile-app-config", options.mobile_app_config),
        _artifact("--private-beta-evidence", options.private_beta_evidence),
        _artifact("--release-notes", options.release_notes),
    ]
    checks = [
        _mobile_release_check(
            options.mobile_release_evidence,
            options.mobile_app_config,
            require_store_submission=options.require_mobile_store_submission,
        ),
        _private_beta_check(options.private_beta_evidence),
        _release_notes_check(options.release_notes, options.release_version),
    ]
    missing = [artifact["flag"] for artifact in artifacts if artifact["status"] == "missing"]
    empty = [artifact["flag"] for artifact in artifacts if artifact["status"] == "empty"]
    invalid = [artifact["flag"] for artifact in artifacts if artifact["status"] == "not-file"]
    failed_checks = [check["name"] for check in checks if check["status"] != "pass"]
    return {
        "ready": not missing and not empty and not invalid and not failed_checks,
        "artifacts": artifacts,
        "checks": checks,
        "missingArtifacts": missing,
        "emptyArtifacts": empty,
        "invalidArtifacts": invalid,
        "failedChecks": failed_checks,
        "runtimeChecksExcluded": True,
        "notes": [
            "Read-only packet status only; it does not replace scripts/release_gate.py.",
            "Git, GitHub Actions, Docker Compose, runtime health, and live VPN boundary checks are intentionally excluded.",
        ],
    }


def _artifact(flag: str, path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"flag": flag, "path": None, "status": "missing", "bytes": 0}
    if not path.exists():
        return {"flag": flag, "path": str(path), "status": "missing", "bytes": 0}
    if not path.is_file():
        return {"flag": flag, "path": str(path), "status": "not-file", "bytes": 0}
    size = path.stat().st_size
    details: dict[str, Any] = {
        "flag": flag,
        "path": str(path),
        "status": "present" if size > 0 else "empty",
        "bytes": size,
    }
    if size > 0:
        details["sha256"] = _sha256_file(path)
    return details


def _mobile_release_check(
    evidence: Path | None,
    app_config: Path,
    *,
    require_store_submission: bool,
) -> dict[str, Any]:
    if evidence is None:
        return _check("mobile-release-evidence", False, {"error": "mobile release evidence path is required"})
    if not evidence.is_file():
        return _check("mobile-release-evidence", False, {"error": "mobile release evidence file is missing"})
    if not app_config.is_file():
        return _check("mobile-release-evidence", False, {"error": "mobile app config file is missing"})
    result = run_mobile_release_gate(
        MobileReleaseGateOptions(
            evidence=evidence,
            app_config=app_config,
            require_store_submission=require_store_submission,
        )
    )
    return _check(
        "mobile-release-evidence",
        bool(result["passed"]),
        {
            "requireStoreSubmission": require_store_submission,
            "failedChecks": [check["name"] for check in result["checks"] if check["status"] != "pass"],
            "evidenceDetails": result["evidenceDetails"],
        },
    )


def _private_beta_check(path: Path | None) -> dict[str, Any]:
    if path is not None and not path.is_file():
        return _check("private-beta-evidence", False, {"error": "private-beta gate output file is missing"})
    return _check_private_beta_evidence(path)


def _release_notes_check(path: Path | None, release_version: str | None) -> dict[str, Any]:
    if path is not None and not path.is_file():
        return _check("release-notes", False, {"error": "release notes file is missing"})
    return _check_release_notes(path, release_version)


def _check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "details": details}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
