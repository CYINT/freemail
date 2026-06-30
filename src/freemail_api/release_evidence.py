from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from .release_gate import ReleaseGateOptions
from .release_packet_status import ReleasePacketStatusOptions


@dataclass(frozen=True)
class ReleaseEvidenceManifestOptions:
    output: Path
    metadata_backup: Path | None = None
    mail_store_backup: Path | None = None
    restore_drill_evidence: Path | None = None
    mobile_release_evidence: Path | None = None
    mobile_app_config: Path = Path("apps/mobile/app.json")
    private_beta_evidence: Path | None = None
    release_notes: Path | None = None
    release_version: str | None = None
    require_mobile_store_submission: bool = False
    force: bool = False
    generated_at: datetime | None = None


def create_release_evidence_manifest(options: ReleaseEvidenceManifestOptions) -> dict[str, Any]:
    generated_at = _format_timestamp(options.generated_at or datetime.now(timezone.utc))
    manifest_dir = options.output.parent
    manifest_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": generated_at,
        "draftOnly": True,
        "releaseVersion": _non_empty(options.release_version),
        "requireMobileStoreSubmission": options.require_mobile_store_submission,
        "releaseGateInputs": {
            "--metadata-backup": _manifest_path(manifest_dir, options.metadata_backup),
            "--mail-store-backup": _manifest_path(manifest_dir, options.mail_store_backup),
            "--restore-drill-evidence": _manifest_path(manifest_dir, options.restore_drill_evidence),
            "--mobile-release-evidence": _manifest_path(manifest_dir, options.mobile_release_evidence),
            "--mobile-app-config": _manifest_path(manifest_dir, options.mobile_app_config),
            "--private-beta-evidence": _manifest_path(manifest_dir, options.private_beta_evidence),
            "--release-notes": _manifest_path(manifest_dir, options.release_notes),
        },
        "releaseBoundary": "VPN-only private beta on freemail.kuzuryu.ai until public release gates are explicitly satisfied.",
        "notes": [
            "Credential-free manifest only; keep backup archives, mobile release evidence, and private-beta evidence outside Git.",
            "This manifest does not replace scripts/release_gate.py or live runtime verification.",
        ],
    }
    _write_json(options.output, payload, force=options.force)
    return {"generatedAt": generated_at, "file": str(options.output)}


def load_release_gate_options_from_manifest(path: Path) -> ReleaseGateOptions:
    payload = _load_json(path)
    inputs = _manifest_inputs(payload)
    return ReleaseGateOptions(
        metadata_backup=_manifest_input_path(path, inputs, "--metadata-backup"),
        mail_store_backup=_manifest_input_path(path, inputs, "--mail-store-backup"),
        restore_drill_evidence=_manifest_input_path(path, inputs, "--restore-drill-evidence"),
        mobile_release_evidence=_manifest_input_path(path, inputs, "--mobile-release-evidence"),
        mobile_app_config=_manifest_input_path(path, inputs, "--mobile-app-config") or Path("apps/mobile/app.json"),
        private_beta_evidence=_manifest_input_path(path, inputs, "--private-beta-evidence"),
        release_notes=_manifest_input_path(path, inputs, "--release-notes"),
        release_version=_manifest_release_version(payload),
        require_mobile_store_submission=payload.get("requireMobileStoreSubmission") is True,
    )


def load_release_packet_status_options_from_manifest(path: Path) -> ReleasePacketStatusOptions:
    payload = _load_json(path)
    inputs = _manifest_inputs(payload)
    return ReleasePacketStatusOptions(
        metadata_backup=_manifest_input_path(path, inputs, "--metadata-backup"),
        mail_store_backup=_manifest_input_path(path, inputs, "--mail-store-backup"),
        restore_drill_evidence=_manifest_input_path(path, inputs, "--restore-drill-evidence"),
        mobile_release_evidence=_manifest_input_path(path, inputs, "--mobile-release-evidence"),
        mobile_app_config=_manifest_input_path(path, inputs, "--mobile-app-config") or Path("apps/mobile/app.json"),
        private_beta_evidence=_manifest_input_path(path, inputs, "--private-beta-evidence"),
        release_notes=_manifest_input_path(path, inputs, "--release-notes"),
        release_version=_manifest_release_version(payload),
        require_mobile_store_submission=payload.get("requireMobileStoreSubmission") is True,
    )


def _manifest_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    inputs = payload.get("releaseGateInputs")
    if not isinstance(inputs, dict):
        raise ValueError("release evidence manifest must contain releaseGateInputs")
    return inputs


def _manifest_release_version(payload: dict[str, Any]) -> str | None:
    value = payload.get("releaseVersion")
    return str(value).strip() if value is not None and str(value).strip() else None


def _manifest_input_path(manifest_path: Path, inputs: dict[str, Any], flag: str) -> Path | None:
    raw_value = inputs.get(flag)
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    value = Path(raw_value)
    return value if value.is_absolute() else (manifest_path.parent / value).resolve()


def _manifest_path(manifest_dir: Path, path: Path | None) -> str:
    if path is None:
        return ""
    target = path if path.is_absolute() else Path.cwd() / path
    try:
        return os.path.relpath(target.resolve(), manifest_dir.resolve())
    except ValueError:
        return str(path)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_empty(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to overwrite release manifest")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
