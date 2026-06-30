from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import dns.resolver

from .dns_policy import verify_dns_posture
from .release_gate import _check
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
    deliverability_evidence: Path | None = None
    metadata_backup: Path | None = None
    mail_store_backup: Path | None = None
    acceptance: Path | None = None
    skip_dns: bool = False
    skip_evidence: bool = False
    health_url: str | None = "https://freemail.kuzuryu.ai/health"
    deployment_url: str | None = "https://freemail.kuzuryu.ai/api/v1/deployment"
    metadata_readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/metadata/readiness"
    readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/mail-core/readiness"
    skip_runtime: bool = False


def run_private_beta_gate(options: PrivateBetaGateOptions) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if not options.skip_runtime:
        checks.extend(
            _check_runtime(
                options.health_url,
                options.deployment_url,
                options.readiness_url,
                "unknown",
                metadata_readiness_url=options.metadata_readiness_url,
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


def _check_dns_posture(options: PrivateBetaGateOptions) -> dict[str, Any]:
    if options.domain is None or options.dns_guidance is None:
        return _check(
            "controlled-domain-dns",
            False,
            {"error": "--domain and --dns-guidance are required unless --skip-dns is set"},
        )
    guidance = _load_json(options.dns_guidance)
    expected_records = [DnsRecord.model_validate(record) for record in guidance.get("records", [])]
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
        _check_deliverability_evidence(options),
        _check_file("metadata-backup-evidence", options.metadata_backup, "--metadata-backup"),
        _check_file("mail-store-backup-evidence", options.mail_store_backup, "--mail-store-backup"),
        _check_acceptance(options.acceptance),
    ]


def _check_mail_flow_evidence(options: PrivateBetaGateOptions) -> dict[str, Any]:
    if options.mail_flow_evidence is None:
        return _check("controlled-mail-flow-evidence", False, {"error": "--mail-flow-evidence is required"})
    payload = _load_json(options.mail_flow_evidence)
    required_domain = str(payload.get("requiredDkimDomain", "")).lower()
    expected_domain = (options.domain or "").lower()
    inbound_found = payload.get("inboundFound")
    submission_found = payload.get("submissionFound")
    passed = (
        payload.get("passed") is True
        and payload.get("inboundAccepted") is True
        and isinstance(inbound_found, dict)
        and payload.get("submissionAccepted") is True
        and isinstance(submission_found, dict)
        and (not expected_domain or required_domain == expected_domain)
    )
    return _check(
        "controlled-mail-flow-evidence",
        passed,
        {
            "path": str(options.mail_flow_evidence),
            "passed": payload.get("passed"),
            "inboundAccepted": payload.get("inboundAccepted"),
            "inboundFound": bool(inbound_found),
            "submissionAccepted": payload.get("submissionAccepted"),
            "submissionFound": bool(submission_found),
            "requiredDkimDomain": payload.get("requiredDkimDomain"),
            "expectedDomain": options.domain,
        },
    )


def _check_deliverability_evidence(options: PrivateBetaGateOptions) -> dict[str, Any]:
    if options.deliverability_evidence is None:
        return _check("deliverability-abuse-evidence", False, {"error": "--deliverability-evidence is required"})
    payload = _load_json(options.deliverability_evidence)
    expected_domain = (options.domain or "").lower()
    evidence_domain = str(payload.get("domain", "")).lower()
    try:
        abuse_complaints = int(payload.get("abuseComplaints", -1))
    except (TypeError, ValueError):
        abuse_complaints = -1
    passed = (
        payload.get("passed") is True
        and bool(str(payload.get("checkedAt", "")).strip())
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
        {
            "path": str(options.deliverability_evidence),
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
    )


def _check_queue_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _check("queue-evidence", False, {"error": "--queue-evidence is required"})
    payload = _load_json(path)
    pending = int(payload.get("pending", payload.get("pendingMessages", 0)) or 0)
    due = int(payload.get("due", payload.get("dueMessages", 0)) or 0)
    passed = payload.get("passed", True) is True and pending == 0 and due == 0
    return _check(
        "queue-evidence",
        passed,
        {"path": str(path), "passed": payload.get("passed", True), "pending": pending, "due": due},
    )


def _check_acceptance(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _check("private-beta-acceptance", False, {"error": "--acceptance is required"})
    payload = _load_json(path)
    boundary = str(payload.get("accessBoundary", ""))
    limitations = payload.get("knownLimitations", [])
    passed = (
        payload.get("accepted") is True
        and bool(str(payload.get("decisionOwner", "")).strip())
        and "vpn" in boundary.lower()
        and isinstance(limitations, list)
        and bool(limitations)
    )
    return _check(
        "private-beta-acceptance",
        passed,
        {
            "path": str(path),
            "accepted": payload.get("accepted"),
            "decisionOwner": payload.get("decisionOwner"),
            "accessBoundary": payload.get("accessBoundary"),
            "knownLimitations": len(limitations) if isinstance(limitations, list) else 0,
        },
    )


def _check_file(name: str, path: Path | None, flag: str) -> dict[str, Any]:
    if path is None:
        return _check(name, False, {"error": f"{flag} is required"})
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    return _check(name, exists and size > 0, _file_evidence_details(path, exists, size))


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


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload
