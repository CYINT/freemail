from datetime import UTC, datetime
import json
import subprocess
import sys

import pytest

from freemail_api.private_beta_acceptance import (
    PrivateBetaAcceptanceOptions,
    collect_private_beta_acceptance,
)


def test_collect_private_beta_acceptance_writes_gate_payload(tmp_path):
    output = tmp_path / "acceptance.json"

    payload = collect_private_beta_acceptance(
        PrivateBetaAcceptanceOptions(
            domain="Example.COM.",
            output=output,
            decision_owner="CEO",
            accepted=True,
            accepted_at=datetime(2026, 6, 30, 0, 0, tzinfo=UTC),
            known_limitations=("Private beta only",),
        )
    )

    assert payload["passed"] is True
    assert payload["accepted"] is True
    assert payload["acceptedAt"] == "2026-06-30T00:00:00Z"
    assert payload["decisionOwner"] == "CEO"
    assert payload["domain"] == "example.com"
    assert payload["knownLimitations"] == ["Private beta only"]
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_collect_private_beta_acceptance_stays_failing_without_explicit_acceptance(tmp_path):
    payload = collect_private_beta_acceptance(
        PrivateBetaAcceptanceOptions(
            domain="example.com",
            output=tmp_path / "acceptance.json",
            decision_owner="CEO",
            accepted=False,
            accepted_at=datetime(2026, 6, 30, tzinfo=UTC),
        )
    )

    assert payload["passed"] is False
    assert payload["accepted"] is False


def test_collect_private_beta_acceptance_rejects_timezone_free_timestamp(tmp_path):
    with pytest.raises(ValueError):
        collect_private_beta_acceptance(
            PrivateBetaAcceptanceOptions(
                domain="example.com",
                output=tmp_path / "acceptance.json",
                decision_owner="CEO",
                accepted=True,
                accepted_at=datetime(2026, 6, 30),
            )
        )


def test_collect_private_beta_acceptance_refuses_overwrite_without_force(tmp_path):
    output = tmp_path / "acceptance.json"
    output.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        collect_private_beta_acceptance(
            PrivateBetaAcceptanceOptions(
                domain="example.com",
                output=output,
                decision_owner="CEO",
            )
        )


def test_collect_private_beta_acceptance_script_exits_success_when_accepted(tmp_path):
    output = tmp_path / "acceptance.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_private_beta_acceptance.py",
            "--domain",
            "example.com",
            "--output",
            str(output),
            "--decision-owner",
            "CEO",
            "--accepted",
            "--accepted-at",
            "2026-06-30T00:00:00Z",
            "--known-limitation",
            "Private beta only",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["passed"] is True


def test_collect_private_beta_acceptance_script_exits_nonzero_when_not_accepted(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_private_beta_acceptance.py",
            "--domain",
            "example.com",
            "--output",
            str(tmp_path / "acceptance.json"),
            "--decision-owner",
            "CEO",
            "--accepted-at",
            "2026-06-30T00:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["accepted"] is False
