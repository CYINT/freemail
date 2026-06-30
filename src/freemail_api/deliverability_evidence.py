from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DeliverabilityEvidenceOptions:
    domain: str
    mail_flow_evidence: Path
    queue_evidence: Path
    output: Path
    spf_aligned: bool = False
    dmarc_aligned: bool = False
    bounce_or_retry_reviewed: bool = False
    abuse_complaints: int = -1
    checked_at: datetime | None = None
    force: bool = False


def collect_deliverability_evidence(options: DeliverabilityEvidenceOptions) -> dict[str, Any]:
    if options.output.exists() and not options.force:
        raise FileExistsError(f"{options.output} already exists; pass --force to overwrite")
    mail_flow = _load_json(options.mail_flow_evidence)
    queue = _load_json(options.queue_evidence)
    checked_at = _format_timestamp(options.checked_at or datetime.now(timezone.utc))
    domain = _normalize_domain(options.domain)
    dkim_domains = {str(value).lower() for value in mail_flow.get("submissionDkimDomains", [])}
    queue_pending = _coerce_int(queue.get("pendingCount", queue.get("pending", -1)))
    queue_due = _coerce_int(queue.get("dueCount", queue.get("due", -1)))
    queue_clear = queue.get("clear") is True and queue_pending == 0 and queue_due == 0
    dkim_aligned = domain in dkim_domains
    passed = (
        mail_flow.get("passed") is True
        and options.spf_aligned
        and options.dmarc_aligned
        and dkim_aligned
        and queue_clear
        and options.bounce_or_retry_reviewed
        and options.abuse_complaints == 0
    )
    payload = {
        "passed": passed,
        "domain": domain,
        "checkedAt": checked_at,
        "spfAligned": options.spf_aligned,
        "dmarcAligned": options.dmarc_aligned,
        "dkimAligned": dkim_aligned,
        "queueReviewed": True,
        "bounceOrRetryReviewed": options.bounce_or_retry_reviewed,
        "abuseComplaints": options.abuse_complaints,
        "queue": {
            "clear": queue_clear,
            "pending": queue_pending,
            "due": queue_due,
            "reviewedAt": queue.get("reviewedAt"),
        },
        "mailFlow": {
            "passed": mail_flow.get("passed"),
            "checkedAt": mail_flow.get("checkedAt"),
            "requiredDkimDomain": mail_flow.get("requiredDkimDomain"),
            "submissionDkimDomains": sorted(dkim_domains),
        },
        "source": "scripts/collect_deliverability_evidence.py",
        "notes": [
            "Generated from controlled mail-flow evidence, queue evidence, and operator deliverability review assertions.",
            "Keep this file credential-free; do not paste mailbox secrets, provider credentials, raw headers, or private keys.",
        ],
    }
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _normalize_domain(domain: str) -> str:
    normalized = domain.strip().lower().rstrip(".")
    if not normalized or "." not in normalized or ".." in normalized:
        raise ValueError("domain must be a fully qualified DNS name")
    return normalized


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("checked_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _coerce_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1
