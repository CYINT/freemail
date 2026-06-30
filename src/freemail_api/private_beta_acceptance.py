from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


DEFAULT_KNOWN_LIMITATIONS = (
    "Private beta only; do not expose FreeMail to the public internet.",
    "Controlled-domain DNS, mail-flow, queue, mail-core apply, deliverability, backup, and restore evidence must be current.",
    "Signed mobile builds and store-submission evidence remain required before app-store release.",
)


@dataclass(frozen=True)
class PrivateBetaAcceptanceOptions:
    domain: str
    output: Path
    decision_owner: str
    accepted: bool = False
    accepted_at: datetime | None = None
    access_boundary: str = "Dragonscale/VPN clients only"
    known_limitations: tuple[str, ...] = field(default_factory=lambda: DEFAULT_KNOWN_LIMITATIONS)
    force: bool = False


def collect_private_beta_acceptance(options: PrivateBetaAcceptanceOptions) -> dict[str, Any]:
    if options.output.exists() and not options.force:
        raise FileExistsError(f"{options.output} already exists; pass --force to overwrite")
    domain = _normalize_domain(options.domain)
    accepted_at = _format_timestamp(options.accepted_at or datetime.now(timezone.utc))
    limitations = _normalize_limitations(options.known_limitations)
    decision_owner = options.decision_owner.strip()
    payload = {
        "accepted": options.accepted,
        "acceptedAt": accepted_at,
        "decisionOwner": decision_owner,
        "accessBoundary": options.access_boundary.strip(),
        "knownLimitations": limitations,
        "domain": domain,
        "source": "scripts/collect_private_beta_acceptance.py",
        "notes": [
            "Credential-free decision-owner acceptance evidence for VPN-only private beta.",
            "Do not use this file as production/public-release approval.",
        ],
    }
    payload["passed"] = _accepted(payload)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _accepted(payload: dict[str, Any]) -> bool:
    return (
        payload.get("accepted") is True
        and bool(str(payload.get("decisionOwner", "")).strip())
        and "vpn" in str(payload.get("accessBoundary", "")).lower()
        and isinstance(payload.get("knownLimitations"), list)
        and bool(payload.get("knownLimitations"))
    )


def _normalize_domain(domain: str) -> str:
    normalized = domain.strip().lower().rstrip(".")
    if not normalized or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", normalized):
        raise ValueError("domain must be a non-empty DNS name")
    if ".." in normalized or "." not in normalized:
        raise ValueError("domain must be a fully qualified DNS name")
    return normalized


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("accepted_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_limitations(limitations: tuple[str, ...]) -> list[str]:
    normalized = [limitation.strip() for limitation in limitations if limitation.strip()]
    if not normalized:
        raise ValueError("known_limitations must include at least one non-empty limitation")
    return normalized
