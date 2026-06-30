from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from . import database
from .backup import export_metadata_backup
from .mail_store_backup import DEFAULT_DOCKER_IMAGE, DEFAULT_VOLUME, run_mail_store_backup


@dataclass(frozen=True)
class BackupEvidenceOptions:
    output_dir: Path
    database_path: str
    mail_store_volume: str = DEFAULT_VOLUME
    image: str = DEFAULT_DOCKER_IMAGE
    force: bool = False
    generated_at: datetime | None = None


def collect_backup_evidence(
    options: BackupEvidenceOptions,
    *,
    mail_store_backup_runner: Callable[..., None] = run_mail_store_backup,
) -> dict[str, Any]:
    generated_at = _format_timestamp(options.generated_at or datetime.now(timezone.utc))
    options.output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = options.output_dir / "metadata.json"
    mail_store_path = options.output_dir / "stalwart-mail-store.tar.gz"
    manifest_path = options.output_dir / "backup-evidence-manifest.json"
    _refuse_overwrite((metadata_path, mail_store_path, manifest_path), force=options.force)

    database.initialize(options.database_path)
    with database.connect(options.database_path) as connection:
        metadata_payload = export_metadata_backup(connection, generated_at=generated_at)
    _write_json(metadata_path, metadata_payload)

    mail_store_backup_runner(volume=options.mail_store_volume, output=mail_store_path, image=options.image)

    manifest = {
        "generatedAt": generated_at,
        "databasePath": str(options.database_path),
        "mailStoreVolume": options.mail_store_volume,
        "artifacts": {
            "--metadata-backup": _artifact(metadata_path),
            "--mail-store-backup": _artifact(mail_store_path),
        },
        "releaseGateInputs": {
            "--metadata-backup": metadata_path.name,
            "--mail-store-backup": mail_store_path.name,
        },
        "sensitive": True,
        "notes": [
            "Metadata backups include DKIM private keys and password hashes; keep this directory encrypted and outside Git.",
            "Mail-store backup archives may contain mailbox content; keep this directory encrypted and outside Git.",
        ],
    }
    _write_json(manifest_path, manifest)
    return {"generatedAt": generated_at, "manifest": str(manifest_path), **manifest}


def _refuse_overwrite(paths: tuple[Path, ...], *, force: bool) -> None:
    if force:
        return
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"backup evidence artifacts already exist; pass --force to overwrite: {', '.join(existing)}")


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256_file(path)}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
