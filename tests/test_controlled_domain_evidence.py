from datetime import UTC, datetime
import json

from freemail_api.controlled_domain_evidence import (
    ControlledDomainEvidenceOptions,
    collect_controlled_domain_evidence,
    load_mailbox_password,
)
from freemail_api.mail_flow_smoke import LocatedMessage, MailFlowResult
from freemail_api.settings import Settings
from freemail_api.stalwart_queue import QueueSummary


def test_collect_controlled_domain_evidence_writes_gate_compatible_packet(tmp_path):
    result = collect_controlled_domain_evidence(
        ControlledDomainEvidenceOptions(
            domain="example.com",
            output_dir=tmp_path,
            email="admin@example.com",
            password="runtime-secret",
            settings=Settings(),
            spf_aligned=True,
            dmarc_aligned=True,
            bounce_or_retry_reviewed=True,
            abuse_complaints=0,
            force=True,
        ),
        mail_flow_runner=fake_mail_flow,
        queue_runner=fake_queue,
        now=datetime(2026, 6, 30, tzinfo=UTC),
    )

    assert result["domain"] == "example.com"
    assert result["collected"] == {
        "observedDns": False,
        "mailFlow": True,
        "queueClear": True,
        "deliverability": True,
    }
    assert "--mail-core-apply-evidence" in result["remainingManualEvidence"]
    manifest = json.loads((tmp_path / "private-beta-evidence-manifest.example.com.json").read_text(encoding="utf-8"))
    mail_flow = json.loads((tmp_path / "mail-flow.example.com.json").read_text(encoding="utf-8"))
    queue = json.loads((tmp_path / "queue.example.com.json").read_text(encoding="utf-8"))
    deliverability = json.loads((tmp_path / "deliverability.example.com.json").read_text(encoding="utf-8"))

    assert manifest["privateBetaGateInputs"]["--mail-flow-evidence"] == "mail-flow.example.com.json"
    assert mail_flow["passed"] is True
    assert queue["clear"] is True
    assert deliverability["passed"] is True
    assert deliverability["dkimAligned"] is True
    assert "runtime-secret" not in (tmp_path / "mail-flow.example.com.json").read_text(encoding="utf-8")


def test_collect_controlled_domain_evidence_keeps_deliverability_failing_without_operator_alignment(tmp_path):
    result = collect_controlled_domain_evidence(
        ControlledDomainEvidenceOptions(
            domain="example.com",
            output_dir=tmp_path,
            email="admin@example.com",
            password="runtime-secret",
            settings=Settings(),
            force=True,
        ),
        mail_flow_runner=fake_mail_flow,
        queue_runner=fake_queue,
        now=datetime(2026, 6, 30, tzinfo=UTC),
    )

    deliverability = json.loads((tmp_path / "deliverability.example.com.json").read_text(encoding="utf-8"))
    assert result["collected"]["deliverability"] is False
    assert deliverability["passed"] is False
    assert deliverability["spfAligned"] is False
    assert deliverability["dmarcAligned"] is False
    assert deliverability["bounceOrRetryReviewed"] is False
    assert deliverability["abuseComplaints"] == -1


def test_collect_controlled_domain_evidence_writes_observed_dns_from_guidance(tmp_path, monkeypatch):
    guidance = tmp_path / "dns-guidance.json"
    guidance.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "type": "MX",
                        "name": "example.com",
                        "value": "10 mail.example.com.",
                        "purpose": "Route mail to FreeMail.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "freemail_api.controlled_domain_evidence.resolve_observed_dns",
        lambda records: [{"type": records[0].type, "name": records[0].name, "values": ["10 mail.example.com."]}],
    )

    collect_controlled_domain_evidence(
        ControlledDomainEvidenceOptions(
            domain="example.com",
            output_dir=tmp_path,
            email="admin@example.com",
            password="runtime-secret",
            settings=Settings(),
            dns_guidance=guidance,
            force=True,
        ),
        mail_flow_runner=fake_mail_flow,
        queue_runner=fake_queue,
        now=datetime(2026, 6, 30, tzinfo=UTC),
    )

    observed = json.loads((tmp_path / "observed-dns.example.com.json").read_text(encoding="utf-8"))
    assert observed["observedAt"] == "2026-06-30T00:00:00Z"
    assert observed["observedRecords"] == [{"type": "MX", "name": "example.com", "values": ["10 mail.example.com."]}]


def test_load_mailbox_password_normalizes_email_key(tmp_path):
    secrets = tmp_path / "mailbox-secrets.json"
    secrets.write_text(json.dumps({"admin@example.com": "secret"}), encoding="utf-8")

    assert load_mailbox_password(secrets, "ADMIN@EXAMPLE.COM") == "secret"


def test_load_mailbox_password_requires_password_source():
    try:
        load_mailbox_password(None, "admin@example.com")
    except ValueError as error:
        assert "Provide --password or --secrets-json" in str(error)
    else:
        raise AssertionError("expected missing password source to fail")


def fake_mail_flow(**_kwargs):
    return MailFlowResult(
        inbound_accepted=True,
        inbound_found=LocatedMessage(folder="INBOX", message_ids=["1"]),
        submission_accepted=True,
        submission_found=LocatedMessage(folder="Sent", message_ids=["2"]),
        submission_dkim_domains=["example.com"],
        required_dkim_domain="example.com",
        marker="123",
        checked_at="2026-06-30T00:00:00Z",
    )


def fake_queue(**_kwargs):
    return QueueSummary(pending_count=0, due_count=0, messages=[], reviewed_at=datetime(2026, 6, 30, tzinfo=UTC))
