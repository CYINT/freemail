from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .private_beta_gate import PrivateBetaGateOptions


EVIDENCE_FILENAMES = {
    "dns_guidance": "dns-guidance.{domain}.json",
    "observed_dns": "observed-dns.{domain}.json",
    "mail_flow": "mail-flow.{domain}.json",
    "queue": "queue.{domain}.json",
    "mail_core_apply": "mail-core-apply.{domain}.json",
    "deliverability": "deliverability.{domain}.json",
    "metadata_backup": "metadata-backup.{domain}.json",
    "mail_store_backup": "stalwart-mail-store.{domain}.tar.gz",
    "restore_drill_evidence": "restore-drill-evidence.{domain}.json",
    "acceptance": "private-beta-acceptance.{domain}.json",
    "manifest": "private-beta-evidence-manifest.{domain}.json",
}


@dataclass(frozen=True)
class PrivateBetaEvidenceTemplateOptions:
    domain: str
    output_dir: Path
    decision_owner: str = ""
    force: bool = False
    checked_at: datetime | None = None


def create_private_beta_evidence_templates(options: PrivateBetaEvidenceTemplateOptions) -> dict[str, Any]:
    domain = _normalize_domain(options.domain)
    checked_at = _format_timestamp(options.checked_at or datetime.now(timezone.utc))
    options.output_dir.mkdir(parents=True, exist_ok=True)

    payloads = {
        "observed_dns": _observed_dns_template(domain),
        "mail_core_apply": _mail_core_apply_template(domain, checked_at),
        "deliverability": _deliverability_template(domain, checked_at),
        "acceptance": _acceptance_template(domain, checked_at, options.decision_owner),
    }
    paths = {
        name: options.output_dir / pattern.format(domain=domain)
        for name, pattern in EVIDENCE_FILENAMES.items()
        if name != "manifest"
    }
    for name, payload in payloads.items():
        _write_json(paths[name], payload, force=options.force)

    manifest_path = options.output_dir / EVIDENCE_FILENAMES["manifest"].format(domain=domain)
    manifest = _manifest_template(domain, checked_at, paths)
    _write_json(manifest_path, manifest, force=options.force)
    return {
        "domain": domain,
        "generatedAt": checked_at,
        "files": {**{name: str(path) for name, path in paths.items()}, "manifest": str(manifest_path)},
    }


def load_private_beta_gate_options_from_manifest(path: Path) -> PrivateBetaGateOptions:
    payload = _load_json(path)
    inputs = payload.get("privateBetaGateInputs")
    if not isinstance(inputs, dict):
        raise ValueError("private-beta evidence manifest must contain privateBetaGateInputs")
    return PrivateBetaGateOptions(
        domain=str(payload.get("domain") or "").strip() or None,
        dns_guidance=_manifest_input_path(path, inputs, "--dns-guidance"),
        observed_dns=_manifest_input_path(path, inputs, "--observed-dns"),
        mail_flow_evidence=_manifest_input_path(path, inputs, "--mail-flow-evidence"),
        queue_evidence=_manifest_input_path(path, inputs, "--queue-evidence"),
        mail_core_apply_evidence=_manifest_input_path(path, inputs, "--mail-core-apply-evidence"),
        deliverability_evidence=_manifest_input_path(path, inputs, "--deliverability-evidence"),
        metadata_backup=_manifest_input_path(path, inputs, "--metadata-backup"),
        mail_store_backup=_manifest_input_path(path, inputs, "--mail-store-backup"),
        restore_drill_evidence=_manifest_input_path(path, inputs, "--restore-drill-evidence"),
        acceptance=_manifest_input_path(path, inputs, "--acceptance"),
    )


def summarize_private_beta_evidence_manifest(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    inputs = payload.get("privateBetaGateInputs")
    if not isinstance(inputs, dict):
        raise ValueError("private-beta evidence manifest must contain privateBetaGateInputs")
    artifacts = [_artifact_status(path, flag, inputs.get(flag)) for flag in sorted(inputs)]
    return {
        "domain": payload.get("domain"),
        "manifest": str(path),
        "draftOnly": payload.get("draftOnly"),
        "ready": all(artifact["ready"] for artifact in artifacts),
        "missingArtifacts": [artifact["flag"] for artifact in artifacts if artifact["status"] == "missing"],
        "emptyArtifacts": [artifact["flag"] for artifact in artifacts if artifact["status"] == "empty"],
        "draftBlockingArtifacts": [
            artifact["flag"] for artifact in artifacts if artifact.get("draftBlocking") is True
        ],
        "artifacts": artifacts,
    }


def _normalize_domain(domain: str) -> str:
    normalized = domain.strip().lower().rstrip(".")
    if not normalized or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", normalized):
        raise ValueError("domain must be a non-empty DNS name")
    if ".." in normalized or "." not in normalized:
        raise ValueError("domain must be a fully qualified DNS name")
    return normalized


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("checked_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _observed_dns_template(domain: str) -> dict[str, Any]:
    return {
        "domain": domain,
        "observedRecords": [
            {
                "type": "MX",
                "name": domain,
                "values": [],
                "evidenceNote": "Fill with live MX answers after controlled-domain DNS propagates.",
            },
            {
                "type": "TXT",
                "name": domain,
                "values": [],
                "evidenceNote": "Fill with SPF TXT answers observed for the controlled domain.",
            },
            {
                "type": "TXT",
                "name": f"_dmarc.{domain}",
                "values": [],
                "evidenceNote": "Fill with DMARC TXT answers observed for the controlled domain.",
            },
            {
                "type": "TXT",
                "name": f"mail._domainkey.{domain}",
                "values": [],
                "evidenceNote": "Fill with DKIM TXT answers for the active selector.",
            },
        ],
    }


def _deliverability_template(domain: str, checked_at: str) -> dict[str, Any]:
    return {
        "passed": False,
        "domain": domain,
        "checkedAt": checked_at,
        "spfAligned": False,
        "dmarcAligned": False,
        "dkimAligned": False,
        "queueReviewed": False,
        "bounceOrRetryReviewed": False,
        "abuseComplaints": -1,
        "notes": [
            "Replace this draft after controlled inbound/outbound smoke tests and queue review.",
            "Do not mark passed true until SPF, DMARC, DKIM, queue, bounce/retry, and abuse checks are verified.",
        ],
    }


def _mail_core_apply_template(domain: str, checked_at: str) -> dict[str, Any]:
    return {
        "applied": False,
        "appliedAt": checked_at,
        "appliedBy": "",
        "domain": domain,
        "applyTool": "FreeMail Stalwart apply workflow",
        "planStatus": {
            "ready": False,
            "operationTypes": [],
            "domains": 0,
            "dkimKeys": 0,
            "accounts": 0,
            "aliases": 0,
            "missingProvisioningSecrets": [],
        },
        "result": {
            "exitCode": None,
            "stdoutSha256": "",
            "stderrSha256": "",
            "operationCounts": {},
        },
        "postApplyReadiness": {
            "mailCoreReady": False,
            "queueClear": False,
        },
        "evidenceNotes": [
            "Record counts, timestamps, readiness, and output hashes only.",
            "Do not paste raw Stalwart output or sensitive values into this file.",
        ],
    }


def _acceptance_template(domain: str, accepted_at: str, decision_owner: str) -> dict[str, Any]:
    return {
        "accepted": False,
        "acceptedAt": accepted_at,
        "decisionOwner": decision_owner,
        "accessBoundary": "Dragonscale/VPN clients only",
        "knownLimitations": [
            "Private beta only; do not expose FreeMail to the public internet.",
            "Controlled-domain DNS, mail-flow, queue, deliverability, backup, and mobile release evidence must be current.",
            "SQLite is the only supported API metadata backend until PostgreSQL adapter work is completed.",
        ],
        "domain": domain,
    }


def _manifest_template(domain: str, generated_at: str, paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "domain": domain,
        "generatedAt": generated_at,
        "draftOnly": True,
        "privateBetaGateInputs": {
            "--dns-guidance": paths["dns_guidance"].name,
            "--observed-dns": paths["observed_dns"].name,
            "--mail-flow-evidence": paths["mail_flow"].name,
            "--queue-evidence": paths["queue"].name,
            "--mail-core-apply-evidence": paths["mail_core_apply"].name,
            "--deliverability-evidence": paths["deliverability"].name,
            "--metadata-backup": paths["metadata_backup"].name,
            "--mail-store-backup": paths["mail_store_backup"].name,
            "--restore-drill-evidence": paths["restore_drill_evidence"].name,
            "--acceptance": paths["acceptance"].name,
        },
        "releaseBoundary": "VPN-only private beta on freemail.kuzuryu.ai until public release gates are explicitly satisfied.",
    }


def _manifest_input_path(manifest_path: Path, inputs: dict[str, Any], flag: str) -> Path | None:
    raw_value = inputs.get(flag)
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    value = Path(raw_value)
    return value if value.is_absolute() else manifest_path.parent / value


def _artifact_status(manifest_path: Path, flag: str, raw_value: Any) -> dict[str, Any]:
    path = _manifest_input_path(manifest_path, {flag: raw_value}, flag)
    details: dict[str, Any] = {"flag": flag, "path": str(path) if path else None}
    if path is None:
        details.update({"status": "missing", "ready": False, "error": "manifest entry must be a non-empty path"})
        return details
    if not path.exists():
        details.update({"status": "missing", "ready": False})
        return details
    if not path.is_file():
        details.update({"status": "not-file", "ready": False})
        return details
    size = path.stat().st_size
    details["bytes"] = size
    if size <= 0:
        details.update({"status": "empty", "ready": False})
        return details
    details["sha256"] = _sha256_file(path)
    draft_blocking = _draft_blocking_marker(path)
    details["draftBlocking"] = draft_blocking
    details.update({"status": "present", "ready": not draft_blocking})
    return details


def _draft_blocking_marker(path: Path) -> bool:
    if path.suffix.lower() != ".json":
        return False
    try:
        payload = _load_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return True
    return any(
        payload.get(field) is False
        for field in (
            "passed",
            "applied",
            "accepted",
        )
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to overwrite draft templates")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
