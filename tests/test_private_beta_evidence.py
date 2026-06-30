from datetime import datetime, timezone
import json
import subprocess
import sys

import pytest

from freemail_api.private_beta_evidence import (
    PrivateBetaEvidenceTemplateOptions,
    create_private_beta_evidence_templates,
)
from freemail_api.private_beta_gate import PrivateBetaGateOptions, run_private_beta_gate


def test_private_beta_evidence_templates_create_draft_packet(tmp_path):
    result = create_private_beta_evidence_templates(
        PrivateBetaEvidenceTemplateOptions(
            domain="Example.COM.",
            output_dir=tmp_path,
            decision_owner="Dan Fredriksen",
            checked_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
    )

    assert result["domain"] == "example.com"
    observed_dns = json.loads((tmp_path / "observed-dns.example.com.json").read_text(encoding="utf-8"))
    deliverability = json.loads((tmp_path / "deliverability.example.com.json").read_text(encoding="utf-8"))
    acceptance = json.loads((tmp_path / "private-beta-acceptance.example.com.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "private-beta-evidence-manifest.example.com.json").read_text(encoding="utf-8"))

    assert observed_dns["observedRecords"][0]["type"] == "MX"
    assert observed_dns["observedRecords"][0]["values"] == []
    assert deliverability["checkedAt"] == "2026-06-30T00:00:00Z"
    assert deliverability["passed"] is False
    assert acceptance["accepted"] is False
    assert acceptance["decisionOwner"] == "Dan Fredriksen"
    assert "vpn" in acceptance["accessBoundary"].lower()
    assert manifest["draftOnly"] is True
    assert "--mail-flow-evidence" in manifest["privateBetaGateInputs"]


def test_private_beta_evidence_templates_do_not_accidentally_pass_gate(tmp_path):
    create_private_beta_evidence_templates(
        PrivateBetaEvidenceTemplateOptions(
            domain="example.com",
            output_dir=tmp_path,
            checked_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
    )
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    mail_flow = tmp_path / "mail-flow.json"
    queue = tmp_path / "queue.json"
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"backup")
    mail_flow.write_text(
        json.dumps(
            {
                "passed": True,
                "checkedAt": "2026-06-30T00:00:00Z",
                "inboundAccepted": True,
                "inboundFound": {"folder": "INBOX", "message_ids": ["1"]},
                "submissionAccepted": True,
                "submissionFound": {"folder": "Sent", "message_ids": ["2"]},
                "requiredDkimDomain": "example.com",
            }
        ),
        encoding="utf-8",
    )
    queue.write_text(
        json.dumps({"passed": True, "pending": 0, "due": 0, "reviewedAt": "2026-06-30T00:00:00Z"}),
        encoding="utf-8",
    )

    result = run_private_beta_gate(
        PrivateBetaGateOptions(
            domain="example.com",
            skip_runtime=True,
            skip_dns=True,
            mail_flow_evidence=mail_flow,
            queue_evidence=queue,
            deliverability_evidence=tmp_path / "deliverability.example.com.json",
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            acceptance=tmp_path / "private-beta-acceptance.example.com.json",
        )
    )

    checks = {check["name"]: check for check in result["checks"]}
    assert result["passed"] is False
    assert checks["deliverability-abuse-evidence"]["status"] == "fail"
    assert checks["private-beta-acceptance"]["status"] == "fail"


def test_private_beta_evidence_templates_refuse_overwrite_without_force(tmp_path):
    options = PrivateBetaEvidenceTemplateOptions(
        domain="example.com",
        output_dir=tmp_path,
        checked_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )
    create_private_beta_evidence_templates(options)

    with pytest.raises(FileExistsError):
        create_private_beta_evidence_templates(options)


def test_private_beta_evidence_templates_reject_invalid_domain(tmp_path):
    with pytest.raises(ValueError):
        create_private_beta_evidence_templates(
            PrivateBetaEvidenceTemplateOptions(domain="localhost", output_dir=tmp_path)
        )


def test_private_beta_evidence_templates_script(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/create_private_beta_evidence_templates.py",
            "--domain",
            "example.com",
            "--output-dir",
            str(tmp_path),
            "--decision-owner",
            "CEO",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["domain"] == "example.com"
    assert (tmp_path / "private-beta-evidence-manifest.example.com.json").is_file()
