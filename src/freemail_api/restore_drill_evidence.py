from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from . import database
from .backup import BACKUP_TABLES, restore_metadata_backup
from .mail_store_backup import DEFAULT_DOCKER_IMAGE, run_mail_store_restore
from .stalwart_plan import PlanOptions, build_apply_plan, build_apply_plan_status


DEFAULT_DRILL_VOLUME = "freemail_stalwart_restore_drill"


@dataclass(frozen=True)
class RestoreDrillEvidenceOptions:
    metadata_backup: Path
    mail_store_backup: Path
    output: Path
    drill_database: Path
    drill_mail_store_volume: str = DEFAULT_DRILL_VOLUME
    image: str = DEFAULT_DOCKER_IMAGE
    force: bool = False
    generated_at: datetime | None = None


def collect_restore_drill_evidence(
    options: RestoreDrillEvidenceOptions,
    *,
    mail_store_restore_runner: Callable[..., None] = run_mail_store_restore,
) -> dict[str, Any]:
    generated_at = _format_timestamp(options.generated_at or datetime.now(timezone.utc))
    _validate_inputs(options)
    _prepare_drill_database(options.drill_database, force=options.force)
    _refuse_output_overwrite(options.output, force=options.force)

    metadata_payload = _read_json(options.metadata_backup)
    database.initialize(str(options.drill_database))
    with database.connect(str(options.drill_database)) as connection:
        restore_metadata_backup(connection, metadata_payload)
        table_counts = _table_counts(connection)
        apply_plan_status = build_apply_plan_status(connection, available_user_secrets=set())
        apply_plan_summary = _apply_plan_summary(connection)

    mail_store_restore_runner(
        volume=options.drill_mail_store_volume,
        backup=options.mail_store_backup,
        image=options.image,
        force=True,
    )

    evidence = {
        "generatedAt": generated_at,
        "credentialFree": True,
        "backupArtifactsSensitive": True,
        "drillTargets": {
            "databasePath": str(options.drill_database),
            "mailStoreVolume": options.drill_mail_store_volume,
            "image": options.image,
        },
        "inputs": {
            "--metadata-backup": _artifact(options.metadata_backup),
            "--mail-store-backup": _artifact(options.mail_store_backup),
        },
        "metadataRestore": {
            "restored": True,
            "tableCounts": table_counts,
        },
        "stalwartApplyPlan": {
            "exported": True,
            "status": apply_plan_status,
            "summary": apply_plan_summary,
        },
        "mailStoreRestore": {
            "restored": True,
            "drillVolume": options.drill_mail_store_volume,
        },
        "notes": [
            "This evidence intentionally excludes metadata row contents, DKIM private keys, password hashes, and mailbox content.",
            "Run this against a non-production drill database path and a dedicated drill mail-store volume.",
        ],
    }
    options.output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(options.output, evidence)
    return {"evidence": str(options.output), **evidence}


def _validate_inputs(options: RestoreDrillEvidenceOptions) -> None:
    missing = [str(path) for path in (options.metadata_backup, options.mail_store_backup) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"restore drill input does not exist: {', '.join(missing)}")
    if options.drill_database.exists() and options.drill_database.is_dir():
        raise IsADirectoryError(f"drill database path is a directory: {options.drill_database}")


def _prepare_drill_database(path: Path, *, force: bool) -> None:
    if not path.exists():
        return
    if not force:
        raise FileExistsError(f"drill database already exists; pass --force to replace it: {path}")
    path.unlink()


def _refuse_output_overwrite(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"restore drill evidence already exists; pass --force to overwrite it: {path}")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"metadata backup must contain a JSON object: {path}")
    return payload


def _table_counts(connection) -> dict[str, int]:
    return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in BACKUP_TABLES}


def _apply_plan_summary(connection) -> dict[str, Any]:
    plan = build_apply_plan(connection, PlanOptions(user_secrets={}, skip_users_without_secret=True))
    return {
        "operations": len(plan),
        "operationTypes": [str(operation.get("object")) for operation in plan],
    }


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
