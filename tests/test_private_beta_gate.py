import json

from freemail_api import private_beta_gate
from freemail_api.private_beta_gate import PrivateBetaGateOptions, run_private_beta_gate


def test_private_beta_gate_runtime_only_checks_vpn_boundary(monkeypatch):
    def fake_fetch(url):
        if url.endswith("/health"):
            return {"status": "ok", "vpnOnly": True, "release": {"commit": "unknown"}}
        if url.endswith("/deployment"):
            return {"exposure": "vpn-only", "publicInternet": False, "requiredBoundary": "Dragonscale/VPN clients only"}
        return {"status": "ready", "tcpReachable": True, "protocolReady": True}

    monkeypatch.setattr("freemail_api.release_gate._fetch_json", fake_fetch)

    result = run_private_beta_gate(PrivateBetaGateOptions(skip_dns=True, skip_evidence=True))

    assert result["passed"] is True
    assert [check["name"] for check in result["checks"]] == [
        "runtime-health",
        "deployment-boundary",
        "mail-core-readiness",
    ]


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
    queue.write_text('\ufeff{"passed": true, "pending": 0, "due": 0}', encoding="utf-8")

    check = private_beta_gate._check_queue_evidence(queue)

    assert check["status"] == "pass"


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
        "deliverability-abuse-evidence",
        "metadata-backup-evidence",
        "mail-store-backup-evidence",
        "private-beta-acceptance",
    ]


def test_private_beta_gate_accepts_complete_beta_evidence(tmp_path):
    mail_flow = tmp_path / "mail-flow.json"
    queue = tmp_path / "queue.json"
    deliverability = tmp_path / "deliverability.json"
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    acceptance = tmp_path / "acceptance.json"

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
    queue.write_text(json.dumps({"passed": True, "pending": 0, "due": 0}), encoding="utf-8")
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

    result = run_private_beta_gate(
        PrivateBetaGateOptions(
            domain="example.com",
            skip_runtime=True,
            skip_dns=True,
            mail_flow_evidence=mail_flow,
            queue_evidence=queue,
            deliverability_evidence=deliverability,
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            acceptance=acceptance,
        )
    )

    assert result["passed"] is True
