from datetime import UTC, datetime
import json
import subprocess
import sys

import pytest

from freemail_api.deliverability_evidence import DeliverabilityEvidenceOptions, collect_deliverability_evidence


def test_collect_deliverability_evidence_writes_private_beta_gate_payload(tmp_path):
    mail_flow = tmp_path / "mail-flow.json"
    queue = tmp_path / "queue.json"
    output = tmp_path / "deliverability.json"
    write_json(
        mail_flow,
        {
            "passed": True,
            "checkedAt": "2026-06-30T00:00:00Z",
            "requiredDkimDomain": "example.com",
            "submissionDkimDomains": ["example.com"],
        },
    )
    write_json(
        queue,
        {
            "clear": True,
            "pendingCount": 0,
            "dueCount": 0,
            "reviewedAt": "2026-06-30T00:01:00Z",
        },
    )

    payload = collect_deliverability_evidence(
        DeliverabilityEvidenceOptions(
            domain="Example.COM.",
            mail_flow_evidence=mail_flow,
            queue_evidence=queue,
            output=output,
            spf_aligned=True,
            dmarc_aligned=True,
            bounce_or_retry_reviewed=True,
            abuse_complaints=0,
            checked_at=datetime(2026, 6, 30, 0, 2, tzinfo=UTC),
        )
    )

    assert payload["passed"] is True
    assert payload["domain"] == "example.com"
    assert payload["checkedAt"] == "2026-06-30T00:02:00Z"
    assert payload["dkimAligned"] is True
    assert payload["queue"]["pending"] == 0
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_collect_deliverability_evidence_fails_for_unclear_queue(tmp_path):
    mail_flow = tmp_path / "mail-flow.json"
    queue = tmp_path / "queue.json"
    output = tmp_path / "deliverability.json"
    write_json(
        mail_flow,
        {
            "passed": True,
            "checkedAt": "2026-06-30T00:00:00Z",
            "submissionDkimDomains": ["example.com"],
        },
    )
    write_json(queue, {"clear": False, "pendingCount": 1, "dueCount": 0})

    payload = collect_deliverability_evidence(
        DeliverabilityEvidenceOptions(
            domain="example.com",
            mail_flow_evidence=mail_flow,
            queue_evidence=queue,
            output=output,
            spf_aligned=True,
            dmarc_aligned=True,
            bounce_or_retry_reviewed=True,
            abuse_complaints=0,
            checked_at=datetime(2026, 6, 30, tzinfo=UTC),
        )
    )

    assert payload["passed"] is False
    assert payload["queue"]["pending"] == 1


def test_collect_deliverability_evidence_refuses_overwrite_without_force(tmp_path):
    mail_flow = tmp_path / "mail-flow.json"
    queue = tmp_path / "queue.json"
    output = tmp_path / "deliverability.json"
    write_json(mail_flow, {"passed": True, "submissionDkimDomains": ["example.com"]})
    write_json(queue, {"clear": True, "pendingCount": 0, "dueCount": 0})
    output.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        collect_deliverability_evidence(
            DeliverabilityEvidenceOptions(
                domain="example.com",
                mail_flow_evidence=mail_flow,
                queue_evidence=queue,
                output=output,
                checked_at=datetime(2026, 6, 30, tzinfo=UTC),
            )
        )


def test_collect_deliverability_evidence_script_exits_success_for_passing_payload(tmp_path):
    mail_flow = tmp_path / "mail-flow.json"
    queue = tmp_path / "queue.json"
    output = tmp_path / "deliverability.json"
    write_json(
        mail_flow,
        {
            "passed": True,
            "checkedAt": "2026-06-30T00:00:00Z",
            "requiredDkimDomain": "example.com",
            "submissionDkimDomains": ["example.com"],
        },
    )
    write_json(queue, {"clear": True, "pendingCount": 0, "dueCount": 0, "reviewedAt": "2026-06-30T00:00:00Z"})

    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_deliverability_evidence.py",
            "--domain",
            "example.com",
            "--mail-flow-evidence",
            str(mail_flow),
            "--queue-evidence",
            str(queue),
            "--output",
            str(output),
            "--spf-aligned",
            "--dmarc-aligned",
            "--bounce-or-retry-reviewed",
            "--abuse-complaints",
            "0",
            "--checked-at",
            "2026-06-30T00:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["passed"] is True


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
