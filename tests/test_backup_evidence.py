from datetime import UTC, datetime
import hashlib
import json

import pytest

from freemail_api import database
from freemail_api.backup_evidence import BackupEvidenceOptions, collect_backup_evidence
from freemail_api.schemas import DomainCreate


def test_collect_backup_evidence_writes_artifacts_and_manifest(tmp_path):
    database_path = tmp_path / "freemail.sqlite"
    database.initialize(str(database_path))
    with database.connect(str(database_path)) as connection:
        database.create_domain(connection, DomainCreate(name="example.com"), "test")

    result = collect_backup_evidence(
        BackupEvidenceOptions(
            output_dir=tmp_path / "backups",
            database_path=str(database_path),
            mail_store_volume="freemail_freemail_stalwart",
            image="alpine:test",
            generated_at=datetime(2026, 6, 30, tzinfo=UTC),
        ),
        mail_store_backup_runner=fake_mail_store_backup,
    )

    output_dir = tmp_path / "backups"
    metadata_path = output_dir / "metadata.json"
    mail_store_path = output_dir / "stalwart-mail-store.tar.gz"
    manifest_path = output_dir / "backup-evidence-manifest.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result["generatedAt"] == "2026-06-30T00:00:00Z"
    assert metadata["tables"]["domains"][0]["name"] == "example.com"
    assert mail_store_path.read_bytes() == b"fake-mail-store-archive"
    assert manifest["sensitive"] is True
    assert manifest["releaseGateInputs"] == {
        "--metadata-backup": "metadata.json",
        "--mail-store-backup": "stalwart-mail-store.tar.gz",
    }
    assert manifest["artifacts"]["--metadata-backup"]["sha256"] == hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    assert manifest["artifacts"]["--mail-store-backup"]["sha256"] == hashlib.sha256(b"fake-mail-store-archive").hexdigest()


def test_collect_backup_evidence_refuses_overwrite_without_force(tmp_path):
    output_dir = tmp_path / "backups"
    output_dir.mkdir()
    (output_dir / "metadata.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="pass --force"):
        collect_backup_evidence(
            BackupEvidenceOptions(output_dir=output_dir, database_path=str(tmp_path / "freemail.sqlite")),
            mail_store_backup_runner=fake_mail_store_backup,
        )


def test_collect_backup_evidence_force_overwrites_existing_artifacts(tmp_path):
    output_dir = tmp_path / "backups"
    output_dir.mkdir()
    (output_dir / "metadata.json").write_text("old", encoding="utf-8")

    collect_backup_evidence(
        BackupEvidenceOptions(output_dir=output_dir, database_path=str(tmp_path / "freemail.sqlite"), force=True),
        mail_store_backup_runner=fake_mail_store_backup,
    )

    payload = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 1


def fake_mail_store_backup(*, volume, output, image):
    assert volume
    assert image
    output.write_bytes(b"fake-mail-store-archive")
