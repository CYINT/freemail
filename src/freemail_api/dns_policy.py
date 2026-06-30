from __future__ import annotations

from dataclasses import dataclass

from .schemas import DnsRecord


@dataclass(frozen=True)
class DnsCheck:
    type: str
    name: str
    expected: str
    found: bool
    observed: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "name": self.name,
            "expected": self.expected,
            "found": self.found,
            "observed": self.observed,
        }


@dataclass(frozen=True)
class DnsPosture:
    domain: str
    ready: bool
    checks: list[DnsCheck]

    def as_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "ready": self.ready,
            "checks": [check.as_dict() for check in self.checks],
        }


def domain_dns_records(*, domain: str, hostname: str, dkim_keys) -> list[DnsRecord]:
    records = [
        DnsRecord(
            type="MX",
            name=domain,
            value=f"10 {hostname}.",
            purpose="Route inbound mail to the FreeMail host.",
        ),
        DnsRecord(
            type="TXT",
            name=domain,
            value="v=spf1 mx -all",
            purpose="Authorize MX hosts for outbound mail during the controlled deployment phase.",
        ),
        DnsRecord(
            type="TXT",
            name=f"_dmarc.{domain}",
            value=f"v=DMARC1; p=quarantine; rua=mailto:postmaster@{domain}",
            purpose="Enable DMARC reporting and quarantine policy for spoofing protection.",
        ),
    ]
    records.extend(
        DnsRecord(
            type="TXT",
            name=str(row["dns_name"]),
            value=str(row["public_txt"]),
            purpose="Publish DKIM public key for message signature verification.",
        )
        for row in dkim_keys
    )
    return records


def verify_dns_posture(
    *,
    domain: str,
    expected_records: list[DnsRecord],
    observed_records: list[dict[str, object]],
) -> DnsPosture:
    observed_index = _observed_index(observed_records)
    checks = []
    for record in expected_records:
        observed_values = observed_index.get((record.type.upper(), record.name.lower()), [])
        found = any(_normalize_dns_value(value) == _normalize_dns_value(record.value) for value in observed_values)
        checks.append(
            DnsCheck(
                type=record.type,
                name=record.name,
                expected=record.value,
                found=found,
                observed=observed_values,
            )
        )
    return DnsPosture(domain=domain, ready=all(check.found for check in checks), checks=checks)


def _observed_index(observed_records: list[dict[str, object]]) -> dict[tuple[str, str], list[str]]:
    index: dict[tuple[str, str], list[str]] = {}
    for record in observed_records:
        record_type = str(record.get("type", "")).upper()
        name = str(record.get("name", "")).lower().rstrip(".")
        values = record.get("values", [])
        if not isinstance(values, list):
            values = [values]
        index.setdefault((record_type, name), []).extend(str(value) for value in values)
    return index


def _normalize_dns_value(value: str) -> str:
    return " ".join(value.strip().rstrip(".").split())
