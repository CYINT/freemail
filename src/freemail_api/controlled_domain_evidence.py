from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from .mail_flow_smoke import MailFlowResult, run_mail_flow_smoke
from .private_beta_evidence import PrivateBetaEvidenceTemplateOptions, create_private_beta_evidence_templates
from .private_beta_gate import resolve_observed_dns
from .schemas import DnsRecord
from .settings import Settings
from .stalwart_queue import QueueSummary, query_queue_with_cli


@dataclass(frozen=True)
class ControlledDomainEvidenceOptions:
    domain: str
    output_dir: Path
    email: str
    password: str
    settings: Settings
    dns_guidance: Path | None = None
    inbound_recipient: str | None = None
    inbound_sender: str = "sender@example.net"
    submission_recipient: str | None = None
    require_dkim_domain: str | None = None
    spf_aligned: bool = False
    dmarc_aligned: bool = False
    bounce_or_retry_reviewed: bool = False
    abuse_complaints: int = -1
    decision_owner: str = ""
    force: bool = False
    verify_tls: bool = False
    poll_attempts: int = 10
    poll_interval_seconds: float = 1.0
    queue_image: str = "ghcr.io/stalwartlabs/cli"
    queue_timeout_seconds: int = 30


def collect_controlled_domain_evidence(
    options: ControlledDomainEvidenceOptions,
    *,
    mail_flow_runner: Callable[..., MailFlowResult] = run_mail_flow_smoke,
    queue_runner: Callable[..., QueueSummary] = query_queue_with_cli,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = _format_timestamp(now or datetime.now(timezone.utc))
    generated = create_private_beta_evidence_templates(
        PrivateBetaEvidenceTemplateOptions(
            domain=options.domain,
            output_dir=options.output_dir,
            decision_owner=options.decision_owner,
            force=options.force,
            checked_at=_parse_timestamp(checked_at),
        )
    )
    files = {name: Path(path) for name, path in generated["files"].items()}
    domain = str(generated["domain"])

    observed_dns = _collect_observed_dns(options.dns_guidance, domain, checked_at)
    if observed_dns is not None:
        _write_json(files["observed_dns"], observed_dns)

    mail_flow = mail_flow_runner(
        email=options.email,
        password=options.password,
        host=options.settings.mail_core_host,
        smtp_port=options.settings.smtp_port,
        submission_port=options.settings.submission_port,
        imap_port=options.settings.imap_port,
        inbound_recipient=options.inbound_recipient or options.email,
        inbound_sender=options.inbound_sender,
        submission_recipient=options.submission_recipient or options.email,
        required_dkim_domain=options.require_dkim_domain or domain,
        poll_attempts=options.poll_attempts,
        poll_interval_seconds=options.poll_interval_seconds,
        verify_tls=options.verify_tls,
    )
    mail_flow_payload = mail_flow.as_dict()
    _write_json(files["mail_flow"], mail_flow_payload)

    queue = queue_runner(image=options.queue_image, timeout_seconds=options.queue_timeout_seconds)
    queue_payload = queue.as_dict()
    _write_json(files["queue"], queue_payload)

    deliverability_payload = _deliverability_evidence(
        domain=domain,
        checked_at=checked_at,
        mail_flow=mail_flow_payload,
        queue=queue_payload,
        spf_aligned=options.spf_aligned,
        dmarc_aligned=options.dmarc_aligned,
        bounce_or_retry_reviewed=options.bounce_or_retry_reviewed,
        abuse_complaints=options.abuse_complaints,
    )
    _write_json(files["deliverability"], deliverability_payload)

    return {
        "domain": domain,
        "generatedAt": checked_at,
        "manifest": str(files["manifest"]),
        "files": {name: str(path) for name, path in files.items()},
        "collected": {
            "observedDns": observed_dns is not None,
            "mailFlow": mail_flow_payload.get("passed") is True,
            "queueClear": queue.clear,
            "deliverability": deliverability_payload["passed"],
        },
        "remainingManualEvidence": [
            "--mail-core-apply-evidence",
            "--metadata-backup",
            "--mail-store-backup",
            "--restore-drill-evidence",
            "--acceptance",
        ],
    }


def load_mailbox_password(path: Path | None, email: str) -> str:
    if path is None:
        raise ValueError("Provide --password or --secrets-json")
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("mailbox secrets JSON must be an object mapping email addresses to passwords")
    try:
        return str(payload[email.lower()])
    except KeyError as error:
        raise ValueError(f"Missing password for {email}") from error


def _collect_observed_dns(path: Path | None, domain: str, observed_at: str) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open(encoding="utf-8-sig") as handle:
        guidance = json.load(handle)
    if not isinstance(guidance, dict):
        raise ValueError("DNS guidance must be a JSON object")
    expected_records = [DnsRecord.model_validate(record) for record in guidance.get("records", [])]
    return {
        "domain": domain,
        "observedAt": observed_at,
        "observedRecords": resolve_observed_dns(expected_records),
    }


def _deliverability_evidence(
    *,
    domain: str,
    checked_at: str,
    mail_flow: dict[str, Any],
    queue: dict[str, Any],
    spf_aligned: bool,
    dmarc_aligned: bool,
    bounce_or_retry_reviewed: bool,
    abuse_complaints: int,
) -> dict[str, Any]:
    dkim_domains = {str(value).lower() for value in mail_flow.get("submissionDkimDomains", [])}
    dkim_aligned = domain.lower() in dkim_domains
    queue_clear = queue.get("clear") is True and int(queue.get("pendingCount", -1)) == 0 and int(queue.get("dueCount", -1)) == 0
    passed = (
        mail_flow.get("passed") is True
        and spf_aligned
        and dmarc_aligned
        and dkim_aligned
        and queue_clear
        and bounce_or_retry_reviewed
        and abuse_complaints == 0
    )
    return {
        "passed": passed,
        "domain": domain,
        "checkedAt": checked_at,
        "spfAligned": spf_aligned,
        "dmarcAligned": dmarc_aligned,
        "dkimAligned": dkim_aligned,
        "queueReviewed": True,
        "bounceOrRetryReviewed": bounce_or_retry_reviewed,
        "abuseComplaints": abuse_complaints,
        "source": "scripts/collect_controlled_domain_evidence.py",
        "notes": [
            "Generated from controlled-domain mail-flow and queue checks.",
            "SPF, DMARC, bounce/retry, and abuse values are operator assertions from the controlled review.",
        ],
    }


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
