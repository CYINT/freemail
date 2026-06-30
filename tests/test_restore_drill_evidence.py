from datetime import UTC, datetime
import hashlib
import json

import pytest

from freemail_api import database
from freemail_api.backup import export_metadata_backup
from freemail_api.restore_drill_evidence import RestoreDrillEvidenceOptions, collect_restore_drill_evidence
from freemail_api.schemas import DomainCreate


def test_collect_restore_drill_evidence_restores_metadata_and_mail_store(tmp_path):
    metadata_backup = _write_metadata_backup(tmp_path)
    mail_store_backup = tmp_path / "stalwart-mail-store.tar.gz"
    mail_store_backup.write_bytes(b"fake-mail-store")
    output = tmp_path / "restore-drill-evidence.json"
    drill_database = tmp_path / "restore-drill.sqlite"
    calls = []

    result = collect_restore_drill_evidence(
        RestoreDrillEvidenceOptions(
            metadata_backup=metadata_backup,
            mail_store_backup=mail_store_backup,
            output=output,
            drill_database=drill_database,
            drill_mail_store_volume="freemail_restore_drill",
            image="alpine:test",
            generated_at=datetime(2026, 6, 30, tzinfo=UTC),
        ),
        mail_store_restore_runner=lambda **kwargs: calls.append(kwargs),
    )

    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert result["generatedAt"] == "2026-06-30T00:00:00Z"
    assert evidence["credentialFree"] is True
    assert evidence["backupArtifactsSensitive"] is True
    assert evidence["metadataRestore"]["restored"] is True
    assert evidence["metadataRestore"]["tableCounts"]["domains"] == 1
    assert evidence["stalwartApplyPlan"]["exported"] is True
    assert "Domain" in evidence["stalwartApplyPlan"]["summary"]["operationTypes"]
    assert evidence["inputs"]["--mail-store-backup"]["sha256"] == hashlib.sha256(b"fake-mail-store").hexdigest()
    assert calls == [
        {
            "volume": "freemail_restore_drill",
            "backup": mail_store_backup,
            "image": "alpine:test",
            "force": True,
        }
    ]


def test_collect_restore_drill_evidence_refuses_existing_drill_database_without_force(tmp_path):
    metadata_backup = _write_metadata_backup(tmp_path)
    mail_store_backup = tmp_path / "stalwart-mail-store.tar.gz"
    mail_store_backup.write_bytes(b"fake-mail-store")
    drill_database = tmp_path / "restore-drill.sqlite"
    drill_database.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="drill database already exists"):
        collect_restore_drill_evidence(
            RestoreDrillEvidenceOptions(
                metadata_backup=metadata_backup,
                mail_store_backup=mail_store_backup,
                output=tmp_path / "restore-drill-evidence.json",
                drill_database=drill_database,
            ),
            mail_store_restore_runner=fake_mail_store_restore,
        )


def test_collect_restore_drill_evidence_refuses_existing_output_without_force(tmp_path):
    metadata_backup = _write_metadata_backup(tmp_path)
    mail_store_backup = tmp_path / "stalwart-mail-store.tar.gz"
    mail_store_backup.write_bytes(b"fake-mail-store")
    output = tmp_path / "restore-drill-evidence.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="restore drill evidence already exists"):
        collect_restore_drill_evidence(
            RestoreDrillEvidenceOptions(
                metadata_backup=metadata_backup,
                mail_store_backup=mail_store_backup,
                output=output,
                drill_database=tmp_path / "restore-drill.sqlite",
            ),
            mail_store_restore_runner=fake_mail_store_restore,
        )


def test_collect_restore_drill_evidence_force_replaces_drill_state(tmp_path):
    metadata_backup = _write_metadata_backup(tmp_path)
    mail_store_backup = tmp_path / "stalwart-mail-store.tar.gz"
    mail_store_backup.write_bytes(b"fake-mail-store")
    output = tmp_path / "restore-drill-evidence.json"
    output.write_text("existing", encoding="utf-8")
    drill_database = tmp_path / "restore-drill.sqlite"
    drill_database.write_text("existing", encoding="utf-8")

    collect_restore_drill_evidence(
        RestoreDrillEvidenceOptions(
            metadata_backup=metadata_backup,
            mail_store_backup=mail_store_backup,
            output=output,
            drill_database=drill_database,
            force=True,
        ),
        mail_store_restore_runner=fake_mail_store_restore,
    )

    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["metadataRestore"]["tableCounts"]["domains"] == 1


def _write_metadata_backup(tmp_path):
    database_path = tmp_path / "freemail.sqlite"
    database.initialize(str(database_path))
    with database.connect(str(database_path)) as connection:
        database.create_domain(connection, DomainCreate(name="example.com"), "test")
        payload = export_metadata_backup(connection, generated_at="2026-06-30T00:00:00Z")
    metadata_backup = tmp_path / "metadata.json"
    metadata_backup.write_text(json.dumps(payload), encoding="utf-8")
    return metadata_backup


def fake_mail_store_restore(**kwargs):
    assert kwargs["force"] is True
