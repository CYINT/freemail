from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import dns.resolver

from .dns_policy import verify_dns_posture
from .release_gate import _check
from .release_gate import _check_runtime
from .schemas import DnsRecord


@dataclass(frozen=True)
class PrivateBetaGateOptions:
    domain: str | None = None
    dns_guidance: Path | None = None
    observed_dns: Path | None = None
    skip_dns: bool = False
    health_url: str | None = "https://freemail.kuzuryu.ai/health"
    deployment_url: str | None = "https://freemail.kuzuryu.ai/api/v1/deployment"
    readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/mail-core/readiness"
    skip_runtime: bool = False


def run_private_beta_gate(options: PrivateBetaGateOptions) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if not options.skip_runtime:
        checks.extend(_check_runtime(options.health_url, options.deployment_url, options.readiness_url, "unknown"))
    if not options.skip_dns:
        checks.append(_check_dns_posture(options))
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
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload
