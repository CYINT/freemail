from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import dns.resolver

from .dns_policy import verify_dns_posture
from .release_gate import _check
from .release_gate import _command
from .release_gate import _check_restore_drill_evidence
from .release_gate import _file_evidence_details
from .release_gate import _check_runtime
from .schemas import DnsRecord


@dataclass(frozen=True)
class PrivateBetaGateOptions:
    domain: str | None = None
    dns_guidance: Path | None = None
    observed_dns: Path | None = None
    mail_flow_evidence: Path | None = None
    queue_evidence: Path | None = None
    mail_core_apply_evidence: Path | None = None
    deliverability_evidence: Path | None = None
    metadata_backup: Path | None = None
    mail_store_backup: Path | None = None
    restore_drill_evidence: Path | None = None
    acceptance: Path | None = None
    skip_dns: bool = False
    skip_evidence: bool = False
    health_url: str | None = "https://freemail.kuzuryu.ai/health"
    deployment_url: str | None = "https://freemail.kuzuryu.ai/api/v1/deployment"
    metadata_readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/metadata/readiness"
    readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/mail-core/readiness"
    apple_app_site_association_url: str | None = "https://freemail.kuzuryu.ai/.well-known/apple-app-site-association"
    assetlinks_url: str | None = "https://freemail.kuzuryu.ai/.well-known/assetlinks.json"
    runtime_commit: str | None = None
    skip_runtime: bool = False


def run_private_beta_gate(options: PrivateBetaGateOptions) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if not options.skip_runtime:
        runtime_commit = _expected_runtime_commit(options)
        checks.extend(
            _check_runtime(
                options.health_url,
                options.deployment_url,
                options.readiness_url,
                runtime_commit,
                metadata_readiness_url=options.metadata_readiness_url,
                apple_app_site_association_url=options.apple_app_site_association_url,
                assetlinks_url=options.assetlinks_url,
            )
        )
    if not options.skip_dns:
        checks.append(_check_dns_posture(options))
    if not options.skip_evidence:
        checks.extend(_check_beta_evidence(options))
    passed = all(check["status"] == "pass" for check in checks)
    return {
        "passed": passed,
        "domain": options.domain,
        "checks": checks,
    }


def _expected_runtime_commit(options: PrivateBetaGateOptions) -> str:
    if options.runtime_commit and options.runtime_commit.strip():
        return options.runtime_commit.strip()
    try:
        return _command(["git", "rev-parse", "HEAD"])
    except Exception:
        return ""


def _check_dns_posture(options: PrivateBetaGateOptions) -> dict[str, Any]:
    if options.domain is None or options.dns_guidance is None:
        return _check(
            "controlled-domain-dns",
            False,
            {"error": "--domain and --dns-guidance are required unless --skip-dns is set"},
        )
    guidance = _load_json(options.dns_guidance)
    expected_records = [DnsRecord.model_validate(record) for record in _dns_guidance_records(guidance)]
    observed_records = _load_observed_dns(options.observed_dns) if options.observed_dns else resolve_observed_dns(expected_records)
    posture = verify_dns_posture(
        domain=options.domain,
        expected_records=expected_records,
        observed_records=observed_records,
    )
    return _check(
        "controlled-domain-dns",
        posture.ready,
        {
            "domain": options.domain,
            "source": str(options.observed_dns) if options.observed_dns else "live-dns",
            "posture": posture.as_dict(),
        },
    )


def _check_beta_evidence(options: PrivateBetaGateOptions) -> list[dict[str, Any]]:
    return [
        _check_mail_flow_evidence(options),
        _check_queue_evidence(options.queue_evidence),
        _check_mail_core_apply_evidence(options),
        _check_deliverability_evidence(options),
        _check_file("metadata-backup-evidence", options.metadata_backup, "--metadata-backup"),
        _check_file("mail-store-backup-evidence", options.mail_store_backup, "--mail-store-backup"),
        _check_private_beta_restore_drill_evidence(options.restore_drill_evidence),
        _check_acceptance(options.acceptance),
    ]


def _check_private_beta_restore_drill_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _check("restore-drill-evidence", False, {"error": "--restore-drill-evidence is required"})
    return _check_restore_drill_evidence(path)


def _check_mail_flow_evidence(options: PrivateBetaGateOptions) -> dict[str, Any]:
    if options.mail_flow_evidence is None:
        return _check("controlled-mail-flow-evidence", False, {"error": "--mail-flow-evidence is required"})
    missing = _missing_json_evidence_check(
        "controlled-mail-flow-evidence",
        options.mail_flow_evidence,
        "mail flow evidence file must exist and be non-empty",
    )
    if missing is not None:
        return missing
    payload = _load_json(options.mail_flow_evidence)
    required_domain = str(payload.get("requiredDkimDomain", "")).lower()
    expected_domain = (options.domain or "").lower()
    inbound_found = payload.get("inboundFound")
    submission_found = payload.get("submissionFound")
    passed = (
        payload.get("passed") is True
        and _is_timezone_aware_iso8601(payload.get("checkedAt"))
        and payload.get("inboundAccepted") is True
        and isinstance(inbound_found, dict)
        and payload.get("submissionAccepted") is True
        and isinstance(submission_found, dict)
        and (not expected_domain or required_domain == expected_domain)
    )
    return _check(
        "controlled-mail-flow-evidence",
        passed,
        _json_evidence_details(
            options.mail_flow_evidence,
            {
                "passed": payload.get("passed"),
                "inboundAccepted": payload.get("inboundAccepted"),
                "inboundFound": bool(inbound_found),
                "submissionAccepted": payload.get("submissionAccepted"),
                "submissionFound": bool(submission_found),
                "requiredDkimDomain": payload.get("requiredDkimDomain"),
                "expectedDomain": options.domain,
                "checkedAt": payload.get("checkedAt"),
            },
        ),
    )


def _check_deliverability_evidence(options: PrivateBetaGateOptions) -> dict[str, Any]:
    if options.deliverability_evidence is None:
        return _check("deliverability-abuse-evidence", False, {"error": "--deliverability-evidence is required"})
    missing = _missing_json_evidence_check(
        "deliverability-abuse-evidence",
        options.deliverability_evidence,
        "deliverability evidence file must exist and be non-empty",
    )
    if missing is not None:
        return missing
    payload = _load_json(options.deliverability_evidence)
    expected_domain = (options.domain or "").lower()
    evidence_domain = str(payload.get("domain", "")).lower()
    try:
        abuse_complaints = int(payload.get("abuseComplaints", -1))
    except (TypeError, ValueError):
        abuse_complaints = -1
    passed = (
        payload.get("passed") is True
        and _is_timezone_aware_iso8601(payload.get("checkedAt"))
        and (not expected_domain or evidence_domain == expected_domain)
        and payload.get("spfAligned") is True
        and payload.get("dmarcAligned") is True
        and payload.get("dkimAligned") is True
        and payload.get("queueReviewed") is True
        and payload.get("bounceOrRetryReviewed") is True
        and abuse_complaints == 0
    )
    return _check(
        "deliverability-abuse-evidence",
        passed,
        _json_evidence_details(
            options.deliverability_evidence,
            {
                "passed": payload.get("passed"),
                "domain": payload.get("domain"),
                "expectedDomain": options.domain,
                "spfAligned": payload.get("spfAligned"),
                "dmarcAligned": payload.get("dmarcAligned"),
                "dkimAligned": payload.get("dkimAligned"),
                "queueReviewed": payload.get("queueReviewed"),
                "bounceOrRetryReviewed": payload.get("bounceOrRetryReviewed"),
                "abuseComplaints": abuse_complaints,
            },
        ),
    )


def _check_queue_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _check("queue-evidence", False, {"error": "--queue-evidence is required"})
    missing = _missing_json_evidence_check("queue-evidence", path, "queue evidence file must exist and be non-empty")
    if missing is not None:
        return missing
    payload = _load_json(path)
    pending = _coerce_int(payload.get("pending", payload.get("pendingCount", payload.get("pendingMessages", 0))))
    due = _coerce_int(payload.get("due", payload.get("dueCount", payload.get("dueMessages", 0))))
    clear = payload.get("clear", pending == 0 and due == 0)
    reviewed_at = payload.get("reviewedAt")
    passed = (
        payload.get("passed", True) is True
        and clear is True
        and pending == 0
        and due == 0
        and _is_timezone_aware_iso8601(reviewed_at)
    )
    return _check(
        "queue-evidence",
        passed,
        _json_evidence_details(
            path,
            {
                "passed": payload.get("passed", True),
                "clear": clear,
                "pending": pending,
                "due": due,
                "reviewedAt": reviewed_at,
            },
        ),
    )


def _check_mail_core_apply_evidence(options: PrivateBetaGateOptions) -> dict[str, Any]:
    if options.mail_core_apply_evidence is None:
        return _check("mail-core-apply-evidence", False, {"error": "--mail-core-apply-evidence is required"})
    missing = _missing_json_evidence_check(
        "mail-core-apply-evidence",
        options.mail_core_apply_evidence,
        "mail-core apply evidence file must exist and be non-empty",
    )
    if missing is not None:
        return missing
    payload = _load_json(options.mail_core_apply_evidence)
    expected_domain = (options.domain or "").lower()
    evidence_domain = str(payload.get("domain", "")).lower()
    plan_status = payload.get("planStatus") if isinstance(payload.get("planStatus"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    readiness = payload.get("postApplyReadiness") if isinstance(payload.get("postApplyReadiness"), dict) else {}
    operation_types = plan_status.get("operationTypes", [])
    operation_names = {str(operation).strip() for operation in operation_types} if isinstance(operation_types, list) else set()
    missing_secrets = plan_status.get("missingProvisioningSecrets", [])
    missing_secrets_count = len(missing_secrets) if isinstance(missing_secrets, list) else -1
    domains = _coerce_int(plan_status.get("domains"))
    accounts = _coerce_int(plan_status.get("accounts"))
    dkim_keys = _coerce_int(plan_status.get("dkimKeys"))
    leaked_sensitive_value = _contains_sensitive_evidence_value(payload)
    passed = (
        payload.get("applied") is True
        and _is_timezone_aware_iso8601(payload.get("appliedAt"))
        and (not expected_domain or evidence_domain == expected_domain)
        and plan_status.get("ready") is True
        and missing_secrets_count == 0
        and domains > 0
        and accounts > 0
        and "Domain" in operation_names
        and "Account" in operation_names
        and (dkim_keys >= 0)
        and result.get("exitCode") == 0
        and readiness.get("mailCoreReady") is True
        and readiness.get("queueClear") is True
        and not leaked_sensitive_value
    )
    return _check(
        "mail-core-apply-evidence",
        passed,
        _json_evidence_details(
            options.mail_core_apply_evidence,
            {
                "applied": payload.get("applied"),
                "appliedAt": payload.get("appliedAt"),
                "domain": payload.get("domain"),
                "expectedDomain": options.domain,
                "planReady": plan_status.get("ready"),
                "operationTypes": sorted(operation_names),
                "domains": domains,
                "dkimKeys": dkim_keys,
                "accounts": accounts,
                "aliases": _coerce_int(plan_status.get("aliases")),
                "missingProvisioningSecrets": missing_secrets_count,
                "exitCode": result.get("exitCode"),
                "mailCoreReady": readiness.get("mailCoreReady"),
                "queueClear": readiness.get("queueClear"),
                "leakedSensitiveValue": leaked_sensitive_value,
            },
        ),
    )


def _check_acceptance(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _check("private-beta-acceptance", False, {"error": "--acceptance is required"})
    missing = _missing_json_evidence_check(
        "private-beta-acceptance",
        path,
        "private-beta acceptance evidence file must exist and be non-empty",
    )
    if missing is not None:
        return missing
    payload = _load_json(path)
    boundary = str(payload.get("accessBoundary", ""))
    limitations = payload.get("knownLimitations", [])
    failed_requirements = _acceptance_failed_requirements(payload, boundary, limitations)
    passed = (
        not failed_requirements
    )
    return _check(
        "private-beta-acceptance",
        passed,
        _json_evidence_details(
            path,
            {
                "accepted": payload.get("accepted"),
                "acceptedAt": payload.get("acceptedAt"),
                "decisionOwner": payload.get("decisionOwner"),
                "accessBoundary": payload.get("accessBoundary"),
                "knownLimitations": len(limitations) if isinstance(limitations, list) else 0,
                "failedRequirements": failed_requirements,
            },
        ),
    )


def _acceptance_failed_requirements(
    payload: dict[str, Any],
    boundary: str,
    limitations: Any,
) -> list[str]:
    failed: list[str] = []
    if payload.get("accepted") is not True:
        failed.append("accepted")
    if not _is_timezone_aware_iso8601(payload.get("acceptedAt")):
        failed.append("acceptedAt")
    if not str(payload.get("decisionOwner", "")).strip():
        failed.append("decisionOwner")
    if "vpn" not in boundary.lower():
        failed.append("accessBoundary-vpn")
    if not isinstance(limitations, list) or not limitations:
        failed.append("knownLimitations")
        return failed
    normalized_limitations = " ".join(str(limitation).lower() for limitation in limitations)
    required_terms = {
        "knownLimitations-private-beta": "private beta",
        "knownLimitations-controlled-domain": "controlled-domain",
        "knownLimitations-mobile": "mobile",
        "knownLimitations-store-submission": "store-submission",
    }
    failed.extend(name for name, term in required_terms.items() if term not in normalized_limitations)
    return failed


def _check_file(name: str, path: Path | None, flag: str) -> dict[str, Any]:
    if path is None:
        return _check(name, False, {"error": f"{flag} is required"})
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    return _check(name, exists and size > 0, _file_evidence_details(path, exists, size))


def _json_evidence_details(path: Path, details: dict[str, Any]) -> dict[str, Any]:
    file_details = _file_evidence_details(path)
    file_details.update(details)
    return file_details


def _missing_json_evidence_check(name: str, path: Path, error: str) -> dict[str, Any] | None:
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    if exists and size > 0:
        return None
    details = _file_evidence_details(path, exists, size)
    details["error"] = error
    return _check(name, False, details)


def resolve_observed_dns(expected_records: list[DnsRecord]) -> list[dict[str, object]]:
    names_by_type = {(record.type.upper(), record.name) for record in expected_records}
    observed = []
    for record_type, name in sorted(names_by_type):
        values = _resolve_values(record_type, name)
        observed.append({"type": record_type, "name": name, "values": values})
    return observed


def _resolve_values(record_type: str, name: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(name, record_type)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
        return []
    if record_type == "MX":
        return [f"{answer.preference} {str(answer.exchange)}" for answer in answers]
    if record_type == "TXT":
        return ["".join(part.decode("utf-8") for part in answer.strings) for answer in answers]
    return [answer.to_text() for answer in answers]


def _load_observed_dns(path: Path | None) -> list[dict[str, object]]:
    if path is None:
        return []
    payload = _load_json(path)
    records = payload.get("observedRecords", payload.get("observed_records", payload.get("records", payload)))
    if not isinstance(records, list):
        raise ValueError(f"{path} must contain a list of observed DNS records")
    return records


def _dns_guidance_records(payload: dict[str, Any]) -> list[object]:
    records = payload.get("records")
    if records is None and isinstance(payload.get("dnsGuidance"), dict):
        records = payload["dnsGuidance"].get("records")
    if records is None:
        return []
    if not isinstance(records, list):
        raise ValueError("DNS guidance records must be a list")
    return records


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _coerce_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return -1


def _contains_sensitive_evidence_value(value: object) -> bool:
    if isinstance(value, dict):
        return any(_contains_sensitive_evidence_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_sensitive_evidence_value(item) for item in value)
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "-----begin ",
            "private key",
            "authorization:",
            "bearer ",
            "api_key=",
            "apikey=",
            "access_token=",
            "refresh_token=",
            "password=",
            "stalwart_password=",
        )
    )


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
