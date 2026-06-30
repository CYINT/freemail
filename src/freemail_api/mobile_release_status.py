from __future__ import annotations

from pathlib import Path
from typing import Any

from .mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate
from .release_gate import _file_evidence_details


def summarize_mobile_release_evidence(
    *,
    evidence: Path,
    app_config: Path = Path("apps/mobile/app.json"),
    require_store_submission: bool = False,
) -> dict[str, Any]:
    if not evidence.exists():
        return _missing_evidence(evidence=evidence, app_config=app_config, require_store_submission=require_store_submission)
    if not evidence.is_file():
        return _not_file_evidence(evidence=evidence, app_config=app_config, require_store_submission=require_store_submission)
    if evidence.stat().st_size <= 0:
        return _empty_evidence(evidence=evidence, app_config=app_config, require_store_submission=require_store_submission)

    result = run_mobile_release_gate(
        MobileReleaseGateOptions(
            evidence=evidence,
            app_config=app_config,
            require_store_submission=require_store_submission,
        )
    )
    failed_checks = [check["name"] for check in result["checks"] if check["status"] != "pass"]
    return {
        "ready": result["passed"],
        "evidence": str(evidence),
        "appConfig": str(app_config),
        "requireStoreSubmission": require_store_submission,
        "failedChecks": failed_checks,
        "evidenceDetails": result["evidenceDetails"],
        "checks": result["checks"],
    }


def _missing_evidence(*, evidence: Path, app_config: Path, require_store_submission: bool) -> dict[str, Any]:
    return _unavailable_evidence(
        evidence=evidence,
        app_config=app_config,
        require_store_submission=require_store_submission,
        status="missing",
        error="mobile release evidence file is missing",
    )


def _not_file_evidence(*, evidence: Path, app_config: Path, require_store_submission: bool) -> dict[str, Any]:
    return _unavailable_evidence(
        evidence=evidence,
        app_config=app_config,
        require_store_submission=require_store_submission,
        status="not-file",
        error="mobile release evidence path is not a file",
    )


def _empty_evidence(*, evidence: Path, app_config: Path, require_store_submission: bool) -> dict[str, Any]:
    details = _file_evidence_details(evidence, exists=True, size=0)
    return {
        "ready": False,
        "evidence": str(evidence),
        "appConfig": str(app_config),
        "requireStoreSubmission": require_store_submission,
        "failedChecks": ["mobile-release-evidence"],
        "evidenceDetails": details,
        "checks": [
            {
                "name": "mobile-release-evidence",
                "status": "fail",
                "details": {**details, "status": "empty", "error": "mobile release evidence file is empty"},
            }
        ],
    }


def _unavailable_evidence(
    *,
    evidence: Path,
    app_config: Path,
    require_store_submission: bool,
    status: str,
    error: str,
) -> dict[str, Any]:
    return {
        "ready": False,
        "evidence": str(evidence),
        "appConfig": str(app_config),
        "requireStoreSubmission": require_store_submission,
        "failedChecks": ["mobile-release-evidence"],
        "evidenceDetails": {"path": str(evidence), "exists": evidence.exists(), "bytes": 0},
        "checks": [
            {
                "name": "mobile-release-evidence",
                "status": "fail",
                "details": {"path": str(evidence), "status": status, "error": error},
            }
        ],
    }
