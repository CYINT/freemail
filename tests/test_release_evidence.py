import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from freemail_api.release_evidence import (
    ReleaseEvidenceManifestOptions,
    create_release_evidence_manifest,
    load_release_gate_options_from_manifest,
    load_release_packet_status_options_from_manifest,
)


def test_release_evidence_manifest_loads_release_gate_and_status_options(tmp_path):
    artifacts = create_artifacts(tmp_path)
    manifest = tmp_path / "release" / "release-evidence-manifest.json"

    result = create_release_evidence_manifest(
        ReleaseEvidenceManifestOptions(
            output=manifest,
            metadata_backup=artifacts["metadata_backup"],
            mail_store_backup=artifacts["mail_store_backup"],
            restore_drill_evidence=artifacts["restore_drill_evidence"],
            mobile_release_evidence=artifacts["mobile_release_evidence"],
            mobile_app_config=artifacts["mobile_app_config"],
            private_beta_evidence=artifacts["private_beta_evidence"],
            release_notes=artifacts["release_notes"],
            release_version="v0.1.0-private-beta",
            require_mobile_store_submission=True,
            generated_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
    )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    gate_options = load_release_gate_options_from_manifest(manifest)
    status_options = load_release_packet_status_options_from_manifest(manifest)
    assert result["file"] == str(manifest)
    assert payload["generatedAt"] == "2026-06-30T00:00:00Z"
    assert payload["releaseVersion"] == "v0.1.0-private-beta"
    assert payload["requireMobileStoreSubmission"] is True
    assert payload["releaseGateInputs"]["--metadata-backup"] == str(Path("..") / "metadata.json")
    assert gate_options.metadata_backup == artifacts["metadata_backup"]
    assert gate_options.restore_drill_evidence == artifacts["restore_drill_evidence"]
    assert gate_options.mobile_app_config == artifacts["mobile_app_config"]
    assert gate_options.release_version == "v0.1.0-private-beta"
    assert gate_options.require_mobile_store_submission is True
    assert status_options.private_beta_evidence == artifacts["private_beta_evidence"]
    assert status_options.require_mobile_store_submission is True


def test_release_packet_status_script_accepts_manifest(tmp_path):
    artifacts = create_artifacts(tmp_path)
    manifest = tmp_path / "release" / "release-evidence-manifest.json"
    create_release_evidence_manifest(
        ReleaseEvidenceManifestOptions(
            output=manifest,
            metadata_backup=artifacts["metadata_backup"],
            mail_store_backup=artifacts["mail_store_backup"],
            restore_drill_evidence=artifacts["restore_drill_evidence"],
            mobile_release_evidence=artifacts["mobile_release_evidence"],
            mobile_app_config=artifacts["mobile_app_config"],
            private_beta_evidence=artifacts["private_beta_evidence"],
            release_notes=artifacts["release_notes"],
            release_version="v0.1.0-private-beta",
            require_mobile_store_submission=True,
        )
    )

    completed = subprocess.run(
        [sys.executable, "scripts/release_packet_status.py", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ready"] is True
    assert payload["failedChecks"] == []


def test_release_packet_status_script_cli_paths_override_manifest(tmp_path):
    artifacts = create_artifacts(tmp_path)
    manifest = tmp_path / "release" / "release-evidence-manifest.json"
    override_notes = tmp_path / "override-release-notes.md"
    override_notes.write_text(
        "# FreeMail v0.2.0-private-beta\n\n"
        "Verification: override release packet passed.\n\n"
        "Known limitations: VPN-only private beta.\n",
        encoding="utf-8",
    )
    create_release_evidence_manifest(
        ReleaseEvidenceManifestOptions(
            output=manifest,
            metadata_backup=artifacts["metadata_backup"],
            mail_store_backup=artifacts["mail_store_backup"],
            restore_drill_evidence=artifacts["restore_drill_evidence"],
            mobile_release_evidence=artifacts["mobile_release_evidence"],
            mobile_app_config=artifacts["mobile_app_config"],
            private_beta_evidence=artifacts["private_beta_evidence"],
            release_notes=artifacts["release_notes"],
            release_version="v0.1.0-private-beta",
        )
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/release_packet_status.py",
            "--manifest",
            str(manifest),
            "--release-notes",
            str(override_notes),
            "--release-version",
            "v0.2.0-private-beta",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    release_notes = next(check for check in payload["checks"] if check["name"] == "release-notes")
    assert release_notes["details"]["path"] == str(override_notes)
    assert release_notes["details"]["version"] == "v0.2.0-private-beta"


def test_create_release_evidence_manifest_script_refuses_overwrite_without_force(tmp_path):
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "scripts/create_release_evidence_manifest.py", "--output", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "already exists" in completed.stderr


def create_artifacts(tmp_path):
    metadata_backup = tmp_path / "metadata.json"
    mail_store_backup = tmp_path / "mail-store.tar.gz"
    restore_drill_evidence = tmp_path / "restore-drill-evidence.json"
    mobile_release_evidence = tmp_path / "mobile-release-evidence.json"
    mobile_app_config = tmp_path / "app.json"
    private_beta_evidence = tmp_path / "private-beta-gate.json"
    release_notes = tmp_path / "release-notes.md"
    metadata_backup.write_text("{}", encoding="utf-8")
    mail_store_backup.write_bytes(b"archive")
    write_json(restore_drill_evidence, valid_restore_drill_evidence())
    write_json(mobile_app_config, valid_mobile_app_config())
    write_json(mobile_release_evidence, valid_mobile_release_evidence())
    write_json(private_beta_evidence, valid_private_beta_evidence())
    release_notes.write_text(
        "# FreeMail v0.1.0-private-beta\n\n"
        "Verification: CI, release gates, and backup evidence passed.\n\n"
        "Known limitations: VPN-only private beta.\n",
        encoding="utf-8",
    )
    return {
        "metadata_backup": metadata_backup,
        "mail_store_backup": mail_store_backup,
        "restore_drill_evidence": restore_drill_evidence,
        "mobile_release_evidence": mobile_release_evidence,
        "mobile_app_config": mobile_app_config,
        "private_beta_evidence": private_beta_evidence,
        "release_notes": release_notes,
    }


def valid_mobile_app_config():
    return {
        "expo": {
            "name": "FreeMail",
            "version": "0.1.0-dev",
            "ios": {"bundleIdentifier": "technology.cyint.freemail"},
            "android": {"package": "technology.cyint.freemail"},
            "extra": {"apiBaseUrl": "https://freemail.kuzuryu.ai"},
        }
    }


def valid_mobile_release_evidence():
    return {
        "app": {
            "name": "FreeMail",
            "version": "0.1.0-dev",
            "apiBaseUrl": "https://freemail.kuzuryu.ai",
        },
        "builds": {
            "ios": {
                "identifier": "technology.cyint.freemail",
                "signed": True,
                "distribution": "private-beta",
                "buildUrl": "https://example.invalid/ios-build",
                "artifact": {"type": "ipa", "bytes": 123, "sha256": "a" * 64},
            },
            "android": {
                "identifier": "technology.cyint.freemail",
                "signed": True,
                "distribution": "private-beta",
                "buildUrl": "https://example.invalid/android-build",
                "artifact": {"type": "aab", "bytes": 456, "sha256": "b" * 64},
            },
        },
        "storeSubmissions": {
            "ios": {
                "store": "app-store-connect",
                "identifier": "technology.cyint.freemail",
                "track": "testflight",
                "submitted": True,
                "submissionUrl": "https://example.invalid/testflight",
                "submittedAt": "2026-06-30T00:00:00Z",
                "reviewState": "processing",
            },
            "android": {
                "store": "play-console",
                "identifier": "technology.cyint.freemail",
                "track": "internal-testing",
                "submitted": True,
                "submissionUrl": "https://example.invalid/play-internal",
                "submittedAt": "2026-06-30T00:00:00Z",
                "reviewState": "draft-release-created",
            },
        },
        "privateBetaBoundary": {
            "hostname": "freemail.kuzuryu.ai",
            "vpnOnly": True,
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        },
    }


def valid_private_beta_evidence():
    return {
        "passed": True,
        "domain": "example.com",
        "checks": [
            {"name": "controlled-domain-dns", "status": "pass", "details": {}},
            {"name": "controlled-mail-flow-evidence", "status": "pass", "details": {}},
            {"name": "queue-evidence", "status": "pass", "details": {}},
            {"name": "mail-core-apply-evidence", "status": "pass", "details": {}},
            {"name": "deliverability-abuse-evidence", "status": "pass", "details": {}},
            {"name": "metadata-backup-evidence", "status": "pass", "details": {}},
            {"name": "mail-store-backup-evidence", "status": "pass", "details": {}},
            {"name": "restore-drill-evidence", "status": "pass", "details": {}},
            {"name": "private-beta-acceptance", "status": "pass", "details": {}},
        ],
    }


def valid_restore_drill_evidence():
    return {
        "credentialFree": True,
        "metadataRestore": {"restored": True, "tableCounts": {"domains": 1}},
        "mailStoreRestore": {"restored": True, "drillVolume": "freemail_stalwart_restore_drill"},
        "stalwartApplyPlan": {"exported": True, "summary": {"operations": 1}},
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
