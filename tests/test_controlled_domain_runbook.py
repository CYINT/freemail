from datetime import datetime, timezone
import json
import subprocess
import sys

import pytest

from freemail_api.controlled_domain_runbook import (
    ControlledDomainRunbookOptions,
    create_controlled_domain_runbook,
)


def test_create_controlled_domain_runbook_writes_credential_free_commands(tmp_path):
    result = create_controlled_domain_runbook(
        ControlledDomainRunbookOptions(
            domain="Example.COM.",
            output=tmp_path / "runbook.json",
            evidence_dir=tmp_path / "private-beta",
            admin_email="Admin@Example.com",
            mobile_release_evidence=tmp_path / "mobile.json",
            generated_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
            write_markdown=True,
        )
    )

    assert result == {
        "domain": "example.com",
        "file": str(tmp_path / "runbook.json"),
        "markdown": str(tmp_path / "runbook.md"),
        "generatedAt": "2026-06-30T00:00:00Z",
        "credentialFree": True,
    }
    payload = json.loads((tmp_path / "runbook.json").read_text(encoding="utf-8"))
    assert payload["domain"] == "example.com"
    assert payload["credentialFree"] is True
    assert "correct horse battery" not in json.dumps(payload)
    commands = {command["id"]: command for command in payload["commands"]}
    assert commands["provision-controlled-domain"]["argv"][:2] == [
        ".\\.venv\\Scripts\\python.exe",
        "scripts\\provision_controlled_domain.py",
    ]
    assert commands["provision-controlled-domain"]["output"] == str(tmp_path / "private-beta" / "dns-guidance.example.com.json")
    assert commands["run-private-beta-gate"]["output"] == str(tmp_path / "private-beta" / "private-beta-gate.example.com.json")
    assert "--manifest" in commands["run-release-gate"]["argv"]
    assert (tmp_path / "runbook.md").read_text(encoding="utf-8").startswith("# FreeMail Controlled-Domain Runbook")


def test_create_controlled_domain_runbook_rejects_mismatched_admin_domain(tmp_path):
    with pytest.raises(ValueError, match="admin email domain must match controlled domain"):
        create_controlled_domain_runbook(
            ControlledDomainRunbookOptions(
                domain="example.com",
                output=tmp_path / "runbook.json",
                evidence_dir=tmp_path / "private-beta",
                admin_email="admin@other.example",
            )
        )


def test_create_controlled_domain_runbook_refuses_overwrite_without_force(tmp_path):
    options = ControlledDomainRunbookOptions(
        domain="example.com",
        output=tmp_path / "runbook.json",
        evidence_dir=tmp_path / "private-beta",
    )
    create_controlled_domain_runbook(options)

    with pytest.raises(FileExistsError):
        create_controlled_domain_runbook(options)


def test_create_controlled_domain_runbook_script(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/create_controlled_domain_runbook.py",
            "--domain",
            "example.com",
            "--output",
            str(tmp_path / "runbook.json"),
            "--evidence-dir",
            str(tmp_path / "private-beta"),
            "--write-markdown",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["domain"] == "example.com"
    assert (tmp_path / "runbook.json").is_file()
    assert (tmp_path / "runbook.md").is_file()
