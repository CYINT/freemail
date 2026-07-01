from __future__ import annotations

from pathlib import Path
from typing import Any

from .mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate
from .release_gate import _file_evidence_details


NEXT_ACTIONS_BY_CHECK = {
    "app-metadata": {
        "id": "refresh-mobile-evidence-template",
        "reason": "mobile app metadata or native build identifiers do not match apps/mobile/app.json",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\create_mobile_release_evidence_template.py --force",
    },
    "ios-signed-build": {
        "id": "record-ios-signed-build",
        "reason": "iOS signed-build evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_mobile_build_evidence.py --platform ios --signed --build-url <https-build-evidence-url> --artifact-sha256 <sha256> --artifact-bytes <bytes>",
    },
    "android-signed-build": {
        "id": "record-android-signed-build",
        "reason": "Android signed-build evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_mobile_build_evidence.py --platform android --signed --build-url <https-build-evidence-url> --artifact-sha256 <sha256> --artifact-bytes <bytes>",
    },
    "ios-device-validation": {
        "id": "record-ios-device-validation",
        "reason": "iOS real-device validation evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_mobile_device_validation.py --platform ios --tested --tester <tester> --device-model <device> --os-version <ios-version> --app-version <app-version> --evidence-url <https-device-evidence-url>",
    },
    "android-device-validation": {
        "id": "record-android-device-validation",
        "reason": "Android real-device validation evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_mobile_device_validation.py --platform android --tested --tester <tester> --device-model <device> --os-version <android-version> --app-version <app-version> --evidence-url <https-device-evidence-url>",
    },
    "ios-store-submission": {
        "id": "record-ios-store-submission",
        "reason": "iOS TestFlight or App Store Connect submission evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_mobile_store_submission.py --platform ios --submitted --submission-url <https-store-submission-url> --review-state <state>",
    },
    "android-store-submission": {
        "id": "record-android-store-submission",
        "reason": "Android Play Console submission evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_mobile_store_submission.py --platform android --submitted --submission-url <https-store-submission-url> --review-state <state>",
    },
    "mobile-release-evidence": {
        "id": "create-mobile-release-evidence-template",
        "reason": "mobile release evidence file is missing, empty, or unreadable",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\create_mobile_release_evidence_template.py",
    },
}


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
        "nextActions": mobile_release_next_actions(result["checks"]),
        "evidenceDetails": result["evidenceDetails"],
        "checks": result["checks"],
    }


def mobile_release_next_actions(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for check in checks:
        if check.get("status") == "pass":
            continue
        action = NEXT_ACTIONS_BY_CHECK.get(str(check.get("name")))
        if action is None:
            continue
        details = check.get("details", {})
        failed_requirements = details.get("failedRequirements") if isinstance(details, dict) else None
        actions.append(
            {
                **action,
                "checks": [check["name"]],
                "failedRequirements": failed_requirements if isinstance(failed_requirements, list) else [],
            }
        )
    return actions


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
        "nextActions": mobile_release_next_actions(
            [
                {
                    "name": "mobile-release-evidence",
                    "status": "fail",
                    "details": {"status": "empty", "error": "mobile release evidence file is empty"},
                }
            ]
        ),
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
        "nextActions": mobile_release_next_actions(
            [
                {
                    "name": "mobile-release-evidence",
                    "status": "fail",
                    "details": {"status": status, "error": error},
                }
            ]
        ),
        "evidenceDetails": {"path": str(evidence), "exists": evidence.exists(), "bytes": 0},
        "checks": [
            {
                "name": "mobile-release-evidence",
                "status": "fail",
                "details": {"path": str(evidence), "status": status, "error": error},
            }
        ],
    }
