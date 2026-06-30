import hashlib
import json

from freemail_api import private_beta_gate
from freemail_api.private_beta_gate import PrivateBetaGateOptions, run_private_beta_gate


def test_private_beta_gate_runtime_only_checks_vpn_boundary(monkeypatch):
    def fake_fetch(url):
        if url.endswith("/health"):
            return {"status": "ok", "vpnOnly": True, "release": {"commit": "abc123"}}
        if url.endswith("/deployment"):
            return {"exposure": "vpn-only", "publicInternet": False, "requiredBoundary": "Dragonscale/VPN clients only"}
        if url.endswith("/metadata/readiness"):
            return {
                "status": "ready",
                "backend": "sqlite",
                "schemaRevision": "sqlite-schema-v1",
                "checks": [{"name": "domains", "status": "pass", "missingColumns": []}],
            }
        return {"status": "ready", "tcpReachable": True, "protocolReady": True}

    monkeypatch.setattr("freemail_api.release_gate._fetch_json", fake_fetch)

    result = run_private_beta_gate(
        PrivateBetaGateOptions(runtime_commit="abc123", skip_dns=True, skip_evidence=True)
    )

    assert result["passed"] is True
    assert [check["name"] for check in result["checks"]] == [
        "runtime-health",
        "deployment-boundary",
        "metadata-readiness",
        "mail-core-readiness",
    ]


def test_private_beta_gate_runtime_rejects_stale_commit(monkeypatch):
    def fake_fetch(url):
        if url.endswith("/health"):
            return {"status": "ok", "vpnOnly": True, "release": {"commit": "old456"}}
        if url.endswith("/deployment"):
            return {"exposure": "vpn-only", "publicInternet": False, "requiredBoundary": "Dragonscale/VPN clients only"}
        if url.endswith("/metadata/readiness"):
            return {
                "status": "ready",
                "backend": "sqlite",
                "schemaRevision": "sqlite-schema-v1",
                "checks": [{"name": "domains", "status": "pass", "missingColumns": []}],
            }
        return {"status": "ready", "tcpReachable": True, "protocolReady": True}

    monkeypatch.setattr("freemail_api.release_gate._fetch_json", fake_fetch)

    result = run_private_beta_gate(
        PrivateBetaGateOptions(runtime_commit="abc123", skip_dns=True, skip_evidence=True)
    )

    assert result["passed"] is False
    assert result["checks"][0]["name"] == "runtime-health"
    assert result["checks"][0]["status"] == "fail"
    assert result["checks"][0]["details"]["releaseCommit"] == "old456"


def test_private_beta_gate_requires_domain_dns_inputs_when_dns_enabled():
    result = run_private_beta_gate(PrivateBetaGateOptions(skip_runtime=True))

    assert result["passed"] is False
    assert result["checks"][0]["name"] == "controlled-domain-dns"
    assert "required" in result["checks"][0]["details"]["error"]


def test_private_beta_gate_accepts_matching_observed_dns(tmp_path):
    guidance = tmp_path / "guidance.json"
    observed = tmp_path / "observed.json"
    guidance.write_text(
        json.dumps(
            {
                "domain": "example.com",
                "records": [
                    {
                        "type": "MX",
                        "name": "example.com",
                        "value": "10 freemail.kuzuryu.ai.",
                        "purpose": "Route inbound mail.",
                    },
                    {
                        "type": "TXT",
                        "name": "example.com",
                        "value": "v=spf1 mx -all",
                        "purpose": "SPF.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    observed.write_text(
        json.dumps(
            {
                "observedRecords": [
                    {"type": "MX", "name": "example.com", "values": ["10 freemail.kuzuryu.ai."]},
                    {"type": "TXT", "name": "example.com", "values": ["v=spf1 mx -all"]},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_private_beta_gate(
        PrivateBetaGateOptions(
            domain="example.com",
            dns_guidance=guidance,
            observed_dns=observed,
            skip_runtime=True,
            skip_evidence=True,
        )
    )

    assert result["passed"] is True
    assert result["checks"][0]["details"]["posture"]["ready"] is True


def test_resolve_observed_dns_reports_missing_answers(monkeypatch):
    def fake_resolve(_name, _record_type):
        raise private_beta_gate.dns.resolver.NoAnswer

    monkeypatch.setattr(private_beta_gate.dns.resolver, "resolve", fake_resolve)

    observed = private_beta_gate.resolve_observed_dns(
        [
            private_beta_gate.DnsRecord(
                type="TXT",
                name="example.com",
                value="v=spf1 mx -all",
                purpose="SPF.",
            )
        ]
    )

    assert observed == [{"type": "TXT", "name": "example.com", "values": []}]


def test_private_beta_gate_accepts_utf8_bom_json_evidence(tmp_path):
    queue = tmp_path / "queue.json"
    queue.write_text(
        '\ufeff{"passed": true, "pending": 0, "due": 0, "reviewedAt": "2026-06-30T00:00:00Z"}',
        encoding="utf-8",
    )

    check = private_beta_gate._check_queue_evidence(queue)

    assert check["status"] == "pass"


def test_private_beta_gate_accepts_queue_helper_output(tmp_path):
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps(
            {
                "passed": True,
                "clear": True,
                "pending": 0,
                "due": 0,
                "pendingCount": 0,
                "dueCount": 0,
                "reviewedAt": "2026-06-30T00:00:00Z",
                "messages": [],
            }
        ),
        encoding="utf-8",
    )

    check = private_beta_gate._check_queue_evidence(queue)

    assert check["status"] == "pass"
    assert check["details"]["reviewedAt"] == "2026-06-30T00:00:00Z"


def test_private_beta_gate_rejects_non_clear_queue_helper_output(tmp_path):
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps(
            {
                "passed": False,
                "clear": False,
                "pendingCount": 2,
                "dueCount": 1,
                "reviewedAt": "2026-06-30T00:00:00Z",
                "messages": [{"id": "q1"}, {"id": "q2"}],
            }
        ),
        encoding="utf-8",
    )

    check = private_beta_gate._check_queue_evidence(queue)

    assert check["status"] == "fail"
    assert check["details"]["pending"] == 2
    assert check["details"]["due"] == 1


def test_private_beta_gate_rejects_malformed_queue_counts(tmp_path):
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps({"passed": True, "pendingCount": "many", "dueCount": 0, "reviewedAt": "2026-06-30T00:00:00Z"}),
        encoding="utf-8",
    )

    check = private_beta_gate._check_queue_evidence(queue)

    assert check["status"] == "fail"
    assert check["details"]["pending"] == -1


def test_private_beta_gate_rejects_queue_without_review_timestamp(tmp_path):
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps({"passed": True, "pending": 0, "due": 0}), encoding="utf-8")

    check = private_beta_gate._check_queue_evidence(queue)

    assert check["status"] == "fail"
    assert check["details"]["reviewedAt"] is None


def test_private_beta_gate_rejects_timezone_free_queue_review_timestamp(tmp_path):
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps({"passed": True, "pending": 0, "due": 0, "reviewedAt": "2026-06-30T00:00:00"}),
        encoding="utf-8",
    )

    check = private_beta_gate._check_queue_evidence(queue)

    assert check["status"] == "fail"
    assert check["details"]["reviewedAt"] == "2026-06-30T00:00:00"


def test_private_beta_gate_rejects_malformed_abuse_complaint_count(tmp_path):
    deliverability = tmp_path / "deliverability.json"
    deliverability.write_text(
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
                "abuseComplaints": "none",
            }
        ),
        encoding="utf-8",
    )

    check = private_beta_gate._check_deliverability_evidence(
        PrivateBetaGateOptions(domain="example.com", deliverability_evidence=deliverability)
    )

    assert check["status"] == "fail"
    assert check["details"]["abuseComplaints"] == -1


def test_private_beta_gate_rejects_malformed_deliverability_checked_at(tmp_path):
    deliverability = tmp_path / "deliverability.json"
    deliverability.write_text(
        json.dumps(
            {
                "passed": True,
                "domain": "example.com",
                "checkedAt": "after DNS review",
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

    check = private_beta_gate._check_deliverability_evidence(
        PrivateBetaGateOptions(domain="example.com", deliverability_evidence=deliverability)
    )

    assert check["status"] == "fail"


def test_private_beta_gate_rejects_timezone_free_deliverability_checked_at(tmp_path):
    deliverability = tmp_path / "deliverability.json"
    deliverability.write_text(
        json.dumps(
            {
                "passed": True,
                "domain": "example.com",
                "checkedAt": "2026-06-30T00:00:00",
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

    check = private_beta_gate._check_deliverability_evidence(
        PrivateBetaGateOptions(domain="example.com", deliverability_evidence=deliverability)
    )

    assert check["status"] == "fail"


def test_private_beta_gate_rejects_acceptance_without_accepted_at(tmp_path):
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text(
        json.dumps(
            {
                "accepted": True,
                "decisionOwner": "CEO",
                "accessBoundary": "Dragonscale/VPN clients only",
                "knownLimitations": ["private beta only"],
            }
        ),
        encoding="utf-8",
    )

    check = private_beta_gate._check_acceptance(acceptance)

    assert check["status"] == "fail"
    assert check["details"]["acceptedAt"] is None


def test_private_beta_gate_rejects_malformed_acceptance_timestamp(tmp_path):
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text(
        json.dumps(
            {
                "accepted": True,
                "acceptedAt": "after review",
                "decisionOwner": "CEO",
                "accessBoundary": "Dragonscale/VPN clients only",
                "knownLimitations": ["private beta only"],
            }
        ),
        encoding="utf-8",
    )

    check = private_beta_gate._check_acceptance(acceptance)

    assert check["status"] == "fail"
    assert check["details"]["acceptedAt"] == "after review"


def test_private_beta_gate_rejects_timezone_free_acceptance_timestamp(tmp_path):
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text(
        json.dumps(
            {
                "accepted": True,
                "acceptedAt": "2026-06-30T00:00:00",
                "decisionOwner": "CEO",
                "accessBoundary": "Dragonscale/VPN clients only",
                "knownLimitations": ["private beta only"],
            }
        ),
        encoding="utf-8",
    )

    check = private_beta_gate._check_acceptance(acceptance)

    assert check["status"] == "fail"
    assert check["details"]["acceptedAt"] == "2026-06-30T00:00:00"


def test_private_beta_gate_rejects_mail_flow_without_checked_at(tmp_path):
    mail_flow = tmp_path / "mail-flow.json"
    mail_flow.write_text(
        json.dumps(
            {
                "passed": True,
                "inboundAccepted": True,
                "inboundFound": {"folder": "INBOX", "message_ids": ["1"]},
                "submissionAccepted": True,
                "submissionFound": {"folder": "Sent", "message_ids": ["2"]},
                "requiredDkimDomain": "example.com",
            }
        ),
        encoding="utf-8",
    )

    check = private_beta_gate._check_mail_flow_evidence(
        PrivateBetaGateOptions(domain="example.com", mail_flow_evidence=mail_flow)
    )

    assert check["status"] == "fail"
    assert check["details"]["checkedAt"] is None


def test_private_beta_gate_rejects_malformed_mail_flow_checked_at(tmp_path):
    mail_flow = tmp_path / "mail-flow.json"
    mail_flow.write_text(
        json.dumps(
            {
                "passed": True,
                "checkedAt": "after smoke",
                "inboundAccepted": True,
                "inboundFound": {"folder": "INBOX", "message_ids": ["1"]},
                "submissionAccepted": True,
                "submissionFound": {"folder": "Sent", "message_ids": ["2"]},
                "requiredDkimDomain": "example.com",
            }
        ),
        encoding="utf-8",
    )

    check = private_beta_gate._check_mail_flow_evidence(
        PrivateBetaGateOptions(domain="example.com", mail_flow_evidence=mail_flow)
    )

    assert check["status"] == "fail"
    assert check["details"]["checkedAt"] == "after smoke"


def test_private_beta_gate_rejects_timezone_free_mail_flow_checked_at(tmp_path):
    mail_flow = tmp_path / "mail-flow.json"
    mail_flow.write_text(
        json.dumps(
            {
                "passed": True,
                "checkedAt": "2026-06-30T00:00:00",
                "inboundAccepted": True,
                "inboundFound": {"folder": "INBOX", "message_ids": ["1"]},
                "submissionAccepted": True,
                "submissionFound": {"folder": "Sent", "message_ids": ["2"]},
                "requiredDkimDomain": "example.com",
            }
        ),
        encoding="utf-8",
    )

    check = private_beta_gate._check_mail_flow_evidence(
        PrivateBetaGateOptions(domain="example.com", mail_flow_evidence=mail_flow)
    )

    assert check["status"] == "fail"
    assert check["details"]["checkedAt"] == "2026-06-30T00:00:00"


def test_private_beta_gate_accepts_mail_core_apply_evidence(tmp_path):
    evidence = tmp_path / "mail-core-apply.json"
    write_mail_core_apply_evidence(evidence)

    check = private_beta_gate._check_mail_core_apply_evidence(
        PrivateBetaGateOptions(domain="example.com", mail_core_apply_evidence=evidence)
    )

    assert check["status"] == "pass"
    assert check["details"]["operationTypes"] == ["Account", "DkimSignature", "Domain"]
    assert check["details"]["sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()


def test_private_beta_gate_rejects_mail_core_apply_evidence_with_sensitive_value(tmp_path):
    evidence = tmp_path / "mail-core-apply.json"
    write_mail_core_apply_evidence(evidence, result={"exitCode": 0, "stdoutSha256": "Bearer leaked"})

    check = private_beta_gate._check_mail_core_apply_evidence(
        PrivateBetaGateOptions(domain="example.com", mail_core_apply_evidence=evidence)
    )

    assert check["status"] == "fail"
    assert check["details"]["leakedSensitiveValue"] is True


def test_private_beta_gate_rejects_mail_core_apply_evidence_without_successful_apply(tmp_path):
    evidence = tmp_path / "mail-core-apply.json"
    write_mail_core_apply_evidence(evidence, applied=False)

    check = private_beta_gate._check_mail_core_apply_evidence(
        PrivateBetaGateOptions(domain="example.com", mail_core_apply_evidence=evidence)
    )

    assert check["status"] == "fail"
    assert check["details"]["applied"] is False


def test_private_beta_gate_requires_beta_evidence_when_enabled():
    result = run_private_beta_gate(
        PrivateBetaGateOptions(
            domain="example.com",
            skip_runtime=True,
            skip_dns=True,
        )
    )

    assert result["passed"] is False
    assert [check["name"] for check in result["checks"]] == [
        "controlled-mail-flow-evidence",
        "queue-evidence",
        "mail-core-apply-evidence",
        "deliverability-abuse-evidence",
        "metadata-backup-evidence",
        "mail-store-backup-evidence",
        "restore-drill-evidence",
        "private-beta-acceptance",
    ]


def test_private_beta_gate_reports_missing_manifest_evidence_files(tmp_path):
    result = run_private_beta_gate(
        PrivateBetaGateOptions(
            domain="example.com",
            skip_runtime=True,
            skip_dns=True,
            mail_flow_evidence=tmp_path / "missing-mail-flow.json",
            queue_evidence=tmp_path / "missing-queue.json",
            mail_core_apply_evidence=tmp_path / "missing-mail-core-apply.json",
            deliverability_evidence=tmp_path / "missing-deliverability.json",
            acceptance=tmp_path / "missing-acceptance.json",
        )
    )

    assert result["passed"] is False
    checks_by_name = {check["name"]: check for check in result["checks"]}
    assert checks_by_name["controlled-mail-flow-evidence"]["details"]["bytes"] == 0
    assert checks_by_name["queue-evidence"]["details"]["bytes"] == 0
    assert checks_by_name["mail-core-apply-evidence"]["details"]["bytes"] == 0
    assert checks_by_name["deliverability-abuse-evidence"]["details"]["bytes"] == 0
    assert checks_by_name["private-beta-acceptance"]["details"]["bytes"] == 0
    assert "must exist" in checks_by_name["controlled-mail-flow-evidence"]["details"]["error"]


def test_private_beta_gate_accepts_complete_beta_evidence(tmp_path):
    mail_flow = tmp_path / "mail-flow.json"
    queue = tmp_path / "queue.json"
    mail_core_apply = tmp_path / "mail-core-apply.json"
    deliverability = tmp_path / "deliverability.json"
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    restore_drill = tmp_path / "restore-drill-evidence.json"
    acceptance = tmp_path / "acceptance.json"

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
    write_mail_core_apply_evidence(mail_core_apply)
    deliverability.write_text(
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
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"backup")
    write_json(restore_drill, valid_restore_drill_evidence())
    acceptance.write_text(
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

    result = run_private_beta_gate(
        PrivateBetaGateOptions(
            domain="example.com",
            skip_runtime=True,
            skip_dns=True,
            mail_flow_evidence=mail_flow,
            queue_evidence=queue,
            mail_core_apply_evidence=mail_core_apply,
            deliverability_evidence=deliverability,
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            restore_drill_evidence=restore_drill,
            acceptance=acceptance,
        )
    )

    assert result["passed"] is True
    checks_by_name = {check["name"]: check for check in result["checks"]}
    assert checks_by_name["controlled-mail-flow-evidence"]["details"]["sha256"] == hashlib.sha256(
        mail_flow.read_bytes()
    ).hexdigest()
    assert checks_by_name["queue-evidence"]["details"]["sha256"] == hashlib.sha256(queue.read_bytes()).hexdigest()
    assert checks_by_name["mail-core-apply-evidence"]["details"]["sha256"] == hashlib.sha256(
        mail_core_apply.read_bytes()
    ).hexdigest()
    assert checks_by_name["deliverability-abuse-evidence"]["details"]["sha256"] == hashlib.sha256(
        deliverability.read_bytes()
    ).hexdigest()
    assert checks_by_name["metadata-backup-evidence"]["details"]["sha256"] == hashlib.sha256(b"{}").hexdigest()
    assert checks_by_name["mail-store-backup-evidence"]["details"]["sha256"] == hashlib.sha256(b"backup").hexdigest()
    assert checks_by_name["restore-drill-evidence"]["details"]["sha256"] == hashlib.sha256(
        restore_drill.read_bytes()
    ).hexdigest()
    assert checks_by_name["private-beta-acceptance"]["details"]["sha256"] == hashlib.sha256(
        acceptance.read_bytes()
    ).hexdigest()


def write_mail_core_apply_evidence(path, **overrides):
    payload = {
        "applied": True,
        "appliedAt": "2026-06-30T00:00:00Z",
        "appliedBy": "operator",
        "domain": "example.com",
        "applyTool": "FreeMail Stalwart apply workflow",
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
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def valid_restore_drill_evidence():
    return {
        "credentialFree": True,
        "metadataRestore": {"restored": True, "tableCounts": {"domains": 1}},
        "mailStoreRestore": {"restored": True, "drillVolume": "freemail_stalwart_restore_drill"},
        "stalwartApplyPlan": {"exported": True, "summary": {"operations": 1}},
    }
