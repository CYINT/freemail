from datetime import datetime, timezone
import json
import subprocess
import sys

import pytest

from freemail_api.private_beta_evidence import (
    PrivateBetaEvidenceTemplateOptions,
    create_private_beta_evidence_templates,
    load_private_beta_gate_options_from_manifest,
    summarize_private_beta_evidence_manifest,
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
    mail_core_apply = json.loads((tmp_path / "mail-core-apply.example.com.json").read_text(encoding="utf-8"))
    deliverability = json.loads((tmp_path / "deliverability.example.com.json").read_text(encoding="utf-8"))
    acceptance = json.loads((tmp_path / "private-beta-acceptance.example.com.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "private-beta-evidence-manifest.example.com.json").read_text(encoding="utf-8"))

    assert observed_dns["observedRecords"][0]["type"] == "MX"
    assert observed_dns["observedRecords"][0]["values"] == []
    assert mail_core_apply["applied"] is False
    assert mail_core_apply["planStatus"]["ready"] is False
    assert deliverability["checkedAt"] == "2026-06-30T00:00:00Z"
    assert deliverability["passed"] is False
    assert acceptance["accepted"] is False
    assert acceptance["decisionOwner"] == "Dan Fredriksen"
    assert "vpn" in acceptance["accessBoundary"].lower()
    assert manifest["draftOnly"] is True
    assert "--mail-flow-evidence" in manifest["privateBetaGateInputs"]
    assert "--mail-core-apply-evidence" in manifest["privateBetaGateInputs"]
    assert manifest["privateBetaGateInputs"]["--restore-drill-evidence"] == "restore-drill-evidence.example.com.json"
    options = load_private_beta_gate_options_from_manifest(tmp_path / "private-beta-evidence-manifest.example.com.json")
    assert options.domain == "example.com"
    assert options.mail_flow_evidence == tmp_path / "mail-flow.example.com.json"
    assert options.queue_evidence == tmp_path / "queue.example.com.json"
    assert options.mail_core_apply_evidence == tmp_path / "mail-core-apply.example.com.json"
    assert options.metadata_backup == tmp_path / "metadata-backup.example.com.json"
    assert options.mail_store_backup == tmp_path / "stalwart-mail-store.example.com.tar.gz"
    assert options.restore_drill_evidence == tmp_path / "restore-drill-evidence.example.com.json"
    status = summarize_private_beta_evidence_manifest(tmp_path / "private-beta-evidence-manifest.example.com.json")
    assert status["ready"] is False
    assert "--mail-flow-evidence" in status["missingArtifacts"]
    assert "--mail-core-apply-evidence" in status["draftBlockingArtifacts"]


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
    restore_drill = tmp_path / "restore-drill-evidence.json"
    mail_flow = tmp_path / "mail-flow.json"
    queue = tmp_path / "queue.json"
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"backup")
    write_json(restore_drill, valid_restore_drill_evidence())
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
            mail_core_apply_evidence=tmp_path / "mail-core-apply.example.com.json",
            deliverability_evidence=tmp_path / "deliverability.example.com.json",
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            restore_drill_evidence=restore_drill,
            acceptance=tmp_path / "private-beta-acceptance.example.com.json",
        )
    )

    checks = {check["name"]: check for check in result["checks"]}
    assert result["passed"] is False
    assert checks["mail-core-apply-evidence"]["status"] == "fail"
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


def test_private_beta_gate_script_accepts_manifest_packet(tmp_path):
    create_private_beta_evidence_templates(
        PrivateBetaEvidenceTemplateOptions(
            domain="example.com",
            output_dir=tmp_path,
            checked_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
    )
    (tmp_path / "mail-flow.example.com.json").write_text(
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
    (tmp_path / "queue.example.com.json").write_text(
        json.dumps({"passed": True, "pending": 0, "due": 0, "reviewedAt": "2026-06-30T00:00:00Z"}),
        encoding="utf-8",
    )
    (tmp_path / "mail-core-apply.example.com.json").write_text(
        json.dumps(
            {
                "applied": True,
                "appliedAt": "2026-06-30T00:00:00Z",
                "appliedBy": "operator",
                "domain": "example.com",
                "planStatus": {
                    "ready": True,
                    "operationTypes": ["Domain", "DkimSignature", "Account"],
                    "domains": 1,
                    "dkimKeys": 1,
                    "accounts": 1,
                    "aliases": 0,
                    "missingProvisioningSecrets": [],
                },
                "result": {"exitCode": 0, "stdoutSha256": "a" * 64, "stderrSha256": "b" * 64},
                "postApplyReadiness": {"mailCoreReady": True, "queueClear": True},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "deliverability.example.com.json").write_text(
        json.dumps(
            {
                "passed": True,
                "domain": "example.com",
                "checkedAt": "2026-06-30T00:00:00Z",
                "spfAligned": True,
                "dmarcAligned": True,
                "dkimAligned": True,
                "queueReviewed": True,
                "bounceOrRetryReviewed": True,
                "abuseComplaints": 0,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "metadata-backup.example.com.json").write_text("{}", encoding="utf-8")
    (tmp_path / "stalwart-mail-store.example.com.tar.gz").write_bytes(b"backup")
    write_json(tmp_path / "restore-drill-evidence.example.com.json", valid_restore_drill_evidence())
    (tmp_path / "private-beta-acceptance.example.com.json").write_text(
        json.dumps(
            {
                "accepted": True,
                "acceptedAt": "2026-06-30T00:00:00Z",
                "decisionOwner": "CEO",
                "accessBoundary": "Dragonscale/VPN clients only",
                "knownLimitations": ["private beta only"],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/private_beta_gate.py",
            "--manifest",
            str(tmp_path / "private-beta-evidence-manifest.example.com.json"),
            "--skip-runtime",
            "--skip-dns",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert {"mail-core-apply-evidence", "restore-drill-evidence"}.issubset(
        {check["name"] for check in payload["checks"]}
    )


def test_private_beta_packet_status_script_accepts_completed_packet(tmp_path):
    _write_complete_manifest_packet(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/private_beta_packet_status.py",
            "--manifest",
            str(tmp_path / "private-beta-evidence-manifest.example.com.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert payload["missingArtifacts"] == []
    assert payload["emptyArtifacts"] == []
    assert payload["draftBlockingArtifacts"] == []
    assert all("sha256" in artifact for artifact in payload["artifacts"])


def _write_complete_manifest_packet(tmp_path):
    create_private_beta_evidence_templates(
        PrivateBetaEvidenceTemplateOptions(
            domain="example.com",
            output_dir=tmp_path,
            checked_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
    )
    (tmp_path / "observed-dns.example.com.json").write_text(
        json.dumps({"observedRecords": [{"type": "MX", "name": "example.com", "values": ["10 mail.example.com."]}]}),
        encoding="utf-8",
    )
    (tmp_path / "mail-flow.example.com.json").write_text(
        json.dumps({"passed": True, "checkedAt": "2026-06-30T00:00:00Z"}),
        encoding="utf-8",
    )
    (tmp_path / "queue.example.com.json").write_text(
        json.dumps({"passed": True, "pending": 0, "due": 0, "reviewedAt": "2026-06-30T00:00:00Z"}),
        encoding="utf-8",
    )
    (tmp_path / "mail-core-apply.example.com.json").write_text(
        json.dumps(
            {
                "applied": True,
                "appliedAt": "2026-06-30T00:00:00Z",
                "domain": "example.com",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "deliverability.example.com.json").write_text(
        json.dumps({"passed": True, "checkedAt": "2026-06-30T00:00:00Z"}),
        encoding="utf-8",
    )
    (tmp_path / "metadata-backup.example.com.json").write_text("{}", encoding="utf-8")
    (tmp_path / "stalwart-mail-store.example.com.tar.gz").write_bytes(b"backup")
    write_json(tmp_path / "restore-drill-evidence.example.com.json", valid_restore_drill_evidence())
    (tmp_path / "private-beta-acceptance.example.com.json").write_text(
        json.dumps({"accepted": True, "acceptedAt": "2026-06-30T00:00:00Z"}),
        encoding="utf-8",
    )


def valid_restore_drill_evidence():
    return {
        "credentialFree": True,
        "metadataRestore": {"restored": True, "tableCounts": {"domains": 1}},
        "mailStoreRestore": {"restored": True, "drillVolume": "freemail_stalwart_restore_drill"},
        "stalwartApplyPlan": {"exported": True, "summary": {"operations": 1}},
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
