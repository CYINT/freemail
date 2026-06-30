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

    result = run_private_beta_gate(PrivateBetaGateOptions(skip_dns=True))

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
