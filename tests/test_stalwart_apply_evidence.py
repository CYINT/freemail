import json
import sqlite3
import subprocess
from datetime import UTC, datetime

from freemail_api.database import create_dkim_key, create_domain, create_mailbox, create_user, initialize
from freemail_api.private_beta_gate import PrivateBetaGateOptions, _check_mail_core_apply_evidence
from freemail_api.schemas import DkimKeyCreate, DomainCreate, MailboxCreate, StoredUserCreate
from freemail_api.stalwart_apply_evidence import (
    StalwartApplyEvidenceOptions,
    collect_stalwart_apply_evidence,
    load_user_secrets,
    write_evidence,
)
from freemail_api.stalwart_queue import QueueSummary


def test_collect_stalwart_apply_evidence_writes_gate_compatible_redacted_summary(tmp_path):
    db_path = _seed_database(tmp_path)
    captured = {}

    def fake_runner(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        return subprocess.CompletedProcess(command, 0, stdout="created account\n", stderr="")

    with sqlite3.connect(db_path) as connection:
        evidence = collect_stalwart_apply_evidence(
            connection,
            StalwartApplyEvidenceOptions(
                domain="example.com",
                user_secrets={"admin@example.com": "mail-secret"},
                applied_by="operator",
                now=datetime(2026, 6, 30, tzinfo=UTC),
            ),
            runner=fake_runner,
            queue_query=lambda **_kwargs: QueueSummary(
                pending_count=0,
                due_count=0,
                messages=[],
                reviewed_at=datetime(2026, 6, 30, tzinfo=UTC),
            ),
            mail_core_probe=lambda *_args, **_kwargs: {"protocolReady": True},
        )

    output = tmp_path / "mail-core-apply.json"
    write_evidence(output, evidence)
    check = _check_mail_core_apply_evidence(
        PrivateBetaGateOptions(domain="example.com", mail_core_apply_evidence=output)
    )

    assert check["status"] == "pass"
    assert evidence["applied"] is True
    assert evidence["appliedAt"] == "2026-06-30T00:00:00Z"
    assert evidence["planStatus"]["operationTypes"] == ["Domain", "DkimSignature", "Account"]
    assert evidence["result"]["operationCounts"] == {"Account": 1, "DkimSignature": 1, "Domain": 1}
    assert "mail-secret" in captured["input"]
    assert "BEGIN PRIVATE KEY" in captured["input"]
    assert "mail-secret" not in json.dumps(evidence)
    assert "BEGIN PRIVATE KEY" not in json.dumps(evidence)
    assert captured["command"][:4] == ["docker", "run", "--rm", "-i"]
    assert captured["command"][-2:] == ["apply", "--stdin"]


def test_collect_stalwart_apply_evidence_records_failed_apply_without_raw_output(tmp_path):
    db_path = _seed_database(tmp_path)

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="failed with password=secret")

    with sqlite3.connect(db_path) as connection:
        evidence = collect_stalwart_apply_evidence(
            connection,
            StalwartApplyEvidenceOptions(
                domain="example.com",
                user_secrets={"admin@example.com": "mail-secret"},
                now=datetime(2026, 6, 30, tzinfo=UTC),
            ),
            runner=fake_runner,
            queue_query=lambda **_kwargs: QueueSummary(
                pending_count=0,
                due_count=0,
                messages=[],
                reviewed_at=datetime(2026, 6, 30, tzinfo=UTC),
            ),
            mail_core_probe=lambda *_args, **_kwargs: {"protocolReady": True},
        )

    assert evidence["applied"] is False
    assert evidence["result"]["exitCode"] == 2
    assert "password=secret" not in json.dumps(evidence)
    assert len(evidence["result"]["stderrSha256"]) == 64


def test_load_user_secrets_normalizes_email_keys(tmp_path):
    path = tmp_path / "secrets.json"
    path.write_text(json.dumps({"Admin@Example.COM": "secret"}), encoding="utf-8")

    assert load_user_secrets(path) == {"admin@example.com": "secret"}


def _seed_database(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    initialize(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        domain = create_domain(connection, DomainCreate(name="example.com"), "test")
        user = create_user(
            connection,
            StoredUserCreate(
                email="admin@example.com",
                displayName="Admin User",
                passwordHash="argon2id-placeholder-hash",
            ),
            "test",
        )
        create_mailbox(
            connection,
            MailboxCreate(userId=int(user["id"]), localPart="admin", domainId=int(domain["id"])),
            "test",
        )
        create_dkim_key(
            connection,
            DkimKeyCreate(domainId=int(domain["id"]), selector="mail"),
            "v=DKIM1; k=rsa; p=public",
            "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "test",
        )
    return db_path
