from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from .mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate
from .mobile_release_status import mobile_release_next_actions
from .release_gate import _check_private_beta_evidence, _check_release_notes, _check_restore_drill_evidence


PRIVATE_BETA_ACTIONS_BY_CHECK = {
    "controlled-domain-dns": {
        "id": "refresh-controlled-domain-dns-evidence",
        "reason": "controlled-domain DNS evidence is missing or not passing",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_controlled_domain_evidence.py --domain <domain> --output-dir .freemail-qa\\private-beta --email <mailbox@example.com> --secrets-json <ignored-secrets-json>",
    },
    "controlled-mail-flow-evidence": {
        "id": "record-controlled-mail-flow-evidence",
        "reason": "controlled-domain mail-flow evidence is missing or not passing",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_controlled_domain_evidence.py --domain <domain> --output-dir .freemail-qa\\private-beta --email <mailbox@example.com> --secrets-json <ignored-secrets-json>",
    },
    "queue-evidence": {
        "id": "record-queue-evidence",
        "reason": "mail queue evidence is missing or not clear",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_controlled_domain_evidence.py --domain <domain> --output-dir .freemail-qa\\private-beta --email <mailbox@example.com> --secrets-json <ignored-secrets-json>",
    },
    "mail-core-apply-evidence": {
        "id": "record-mail-core-apply-evidence",
        "reason": "mail-core apply evidence is missing or not passing",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_stalwart_apply_evidence.py --domain <domain> --secrets-json <ignored-secrets-json> --output .freemail-qa\\private-beta\\mail-core-apply.<domain>.json",
    },
    "deliverability-abuse-evidence": {
        "id": "record-deliverability-abuse-evidence",
        "reason": "deliverability and abuse review evidence is missing or not passing",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_deliverability_evidence.py --domain <domain> --mail-flow-evidence .freemail-qa\\private-beta\\mail-flow.<domain>.json --queue-evidence .freemail-qa\\private-beta\\queue.<domain>.json --spf-aligned --dmarc-aligned --bounce-or-retry-reviewed --abuse-complaints 0 --output .freemail-qa\\private-beta\\deliverability.<domain>.json",
    },
    "metadata-backup-evidence": {
        "id": "record-metadata-backup-evidence",
        "reason": "metadata backup evidence is missing",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_backup_evidence.py --output-dir .freemail-qa\\backups --force",
    },
    "mail-store-backup-evidence": {
        "id": "record-mail-store-backup-evidence",
        "reason": "mail-store backup evidence is missing",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_backup_evidence.py --output-dir .freemail-qa\\backups --force",
    },
    "restore-drill-evidence": {
        "id": "record-restore-drill-evidence",
        "reason": "restore-drill evidence is missing or not passing",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_restore_drill_evidence.py --metadata-backup .freemail-qa\\backups\\metadata.json --mail-store-backup .freemail-qa\\backups\\stalwart-mail-store.tar.gz --output .freemail-qa\\backups\\restore-drill-evidence.json --force",
    },
    "private-beta-acceptance": {
        "id": "record-private-beta-acceptance",
        "reason": "decision-owner private-beta acceptance evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_private_beta_acceptance.py --domain <domain> --output .freemail-qa\\private-beta\\private-beta-acceptance.<domain>.json --decision-owner <decision-owner> --accepted --accepted-at <iso-8601>",
    },
}


@dataclass(frozen=True)
class ReleasePacketStatusOptions:
    metadata_backup: Path | None = None
    mail_store_backup: Path | None = None
    restore_drill_evidence: Path | None = None
    mobile_release_evidence: Path | None = None
    mobile_app_config: Path = Path("apps/mobile/app.json")
    private_beta_evidence: Path | None = None
    release_notes: Path | None = None
    release_version: str | None = None
    require_mobile_store_submission: bool = False
    allow_pre_store_mobile_packet: bool = False


def summarize_release_packet(options: ReleasePacketStatusOptions) -> dict[str, Any]:
    artifacts = [
        _artifact("--metadata-backup", options.metadata_backup),
        _artifact("--mail-store-backup", options.mail_store_backup),
        _artifact("--restore-drill-evidence", options.restore_drill_evidence),
        _artifact("--mobile-release-evidence", options.mobile_release_evidence),
        _artifact("--mobile-app-config", options.mobile_app_config),
        _artifact("--private-beta-evidence", options.private_beta_evidence),
        _artifact("--release-notes", options.release_notes),
    ]
    checks = [
        _restore_drill_check(options.restore_drill_evidence),
        _mobile_release_check(
            options.mobile_release_evidence,
            options.mobile_app_config,
            require_store_submission=options.require_mobile_store_submission,
        ),
        _mobile_store_submission_requirement_check(
            options.mobile_release_evidence,
            require_store_submission=options.require_mobile_store_submission,
            allow_pre_store_packet=options.allow_pre_store_mobile_packet,
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
            "Git, GitHub Actions, Docker Compose, runtime health, runtime security headers, and live VPN boundary checks are intentionally excluded.",
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
            "failedRequirements": _mobile_failed_requirements(result["checks"]),
            "nextActions": mobile_release_next_actions(result["checks"]),
            "evidenceDetails": result["evidenceDetails"],
        },
    )


def _mobile_failed_requirements(checks: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        check["name"]: list(failed_requirements)
        for check in checks
        for failed_requirements in [check.get("details", {}).get("failedRequirements")]
        if check["status"] != "pass" and isinstance(failed_requirements, list) and failed_requirements
    }


def _mobile_store_submission_requirement_check(
    evidence: Path | None,
    *,
    require_store_submission: bool,
    allow_pre_store_packet: bool,
) -> dict[str, Any]:
    if evidence is None or not evidence.is_file():
        return _check(
            "mobile-store-submission-requirement",
            True,
            {"skipped": True, "reason": "mobile release evidence file is not available"},
        )
    return _check(
        "mobile-store-submission-requirement",
        require_store_submission or allow_pre_store_packet,
        {
            "requireStoreSubmission": require_store_submission,
            "allowPreStoreMobilePacket": allow_pre_store_packet,
            "error": None
            if require_store_submission or allow_pre_store_packet
            else "release packet status must require mobile store-submission evidence; use --allow-pre-store-mobile-packet only for pre-store dry runs",
        },
    )


def _restore_drill_check(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _check("restore-drill-evidence", False, {"error": "restore drill evidence path is required"})
    if not path.is_file():
        return _check("restore-drill-evidence", False, {"error": "restore drill evidence file is missing"})
    return _check_restore_drill_evidence(path)


def _private_beta_check(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _check(
            "private-beta-evidence",
            False,
            {
                "error": "private-beta gate output path is required",
                "nextActions": [_create_private_beta_template_action()],
            },
        )
    if path is not None and not path.is_file():
        return _check(
            "private-beta-evidence",
            False,
            {
                "error": "private-beta gate output file is missing",
                "nextActions": [_create_private_beta_template_action(), _run_private_beta_gate_action()],
            },
        )
    check = _check_private_beta_evidence(path)
    details = check.get("details")
    if isinstance(details, dict):
        details["nextActions"] = _private_beta_next_actions(details)
    return check


def _private_beta_next_actions(details: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    missing_checks = details.get("missingChecks")
    failed_checks = details.get("failedChecks")
    failed_requirements = details.get("failedRequirements")
    failed_requirements_by_check = failed_requirements if isinstance(failed_requirements, dict) else {}
    for check_name in _private_beta_action_check_names(missing_checks, failed_checks, failed_requirements_by_check):
        action = PRIVATE_BETA_ACTIONS_BY_CHECK.get(check_name)
        if action is None:
            continue
        actions.append(
            {
                **action,
                "checks": [check_name],
                "failedRequirements": list(failed_requirements_by_check.get(check_name, [])),
            }
        )
    if actions:
        actions.append(_run_private_beta_gate_action())
    return actions


def _private_beta_action_check_names(
    missing_checks: Any,
    failed_checks: Any,
    failed_requirements_by_check: dict[str, Any],
) -> list[str]:
    names = []
    for value in [missing_checks, failed_checks, list(failed_requirements_by_check)]:
        if not isinstance(value, list):
            continue
        for name in value:
            if isinstance(name, str) and name not in names:
                names.append(name)
    return names


def _create_private_beta_template_action() -> dict[str, Any]:
    return {
        "id": "create-private-beta-evidence-templates",
        "reason": "private-beta evidence packet is missing",
        "checks": ["private-beta-evidence"],
        "failedRequirements": [],
        "command": ".\\.venv\\Scripts\\python.exe scripts\\create_private_beta_evidence_templates.py --domain <domain> --output-dir .freemail-qa\\private-beta",
    }


def _run_private_beta_gate_action() -> dict[str, Any]:
    return {
        "id": "run-private-beta-gate",
        "reason": "refresh the private-beta gate output after collecting evidence",
        "checks": ["private-beta-evidence"],
        "failedRequirements": [],
        "command": ".\\.venv\\Scripts\\python.exe scripts\\private_beta_gate.py --manifest .freemail-qa\\private-beta\\private-beta-evidence-manifest.<domain>.json",
    }


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
