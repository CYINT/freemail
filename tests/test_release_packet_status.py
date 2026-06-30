import hashlib
import json
import subprocess
import sys

from freemail_api.release_packet_status import ReleasePacketStatusOptions, summarize_release_packet


def test_release_packet_status_reports_missing_artifacts(tmp_path):
    result = summarize_release_packet(
        ReleasePacketStatusOptions(
            metadata_backup=tmp_path / "missing-metadata.json",
            mail_store_backup=tmp_path / "missing-mail-store.tar.gz",
            restore_drill_evidence=tmp_path / "missing-restore-drill.json",
            mobile_release_evidence=tmp_path / "missing-mobile.json",
            mobile_app_config=tmp_path / "missing-app.json",
            private_beta_evidence=tmp_path / "missing-private-beta.json",
            release_notes=tmp_path / "missing-release-notes.md",
        )
    )

    assert result["ready"] is False
    assert result["missingArtifacts"] == [
        "--metadata-backup",
        "--mail-store-backup",
        "--restore-drill-evidence",
        "--mobile-release-evidence",
        "--mobile-app-config",
        "--private-beta-evidence",
        "--release-notes",
    ]
    assert result["failedChecks"] == ["mobile-release-evidence", "private-beta-evidence", "release-notes"]
    assert result["runtimeChecksExcluded"] is True


def test_release_packet_status_reports_mobile_draft_failures(tmp_path):
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    mobile_evidence = tmp_path / "mobile-release-evidence.json"
    restore_drill = tmp_path / "restore-drill-evidence.json"
    mobile_app_config = tmp_path / "app.json"
    private_beta_evidence = tmp_path / "private-beta-gate.json"
    release_notes = tmp_path / "release-notes.md"
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"archive")
    write_json(restore_drill, valid_restore_drill_evidence())
    write_json(mobile_app_config, valid_mobile_app_config())
    mobile_payload = valid_mobile_release_evidence()
    mobile_payload["builds"]["ios"]["signed"] = False
    write_json(mobile_evidence, mobile_payload)
    write_json(private_beta_evidence, valid_private_beta_evidence())
    write_release_notes(release_notes)

    result = summarize_release_packet(
        ReleasePacketStatusOptions(
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            restore_drill_evidence=restore_drill,
            mobile_release_evidence=mobile_evidence,
            mobile_app_config=mobile_app_config,
            private_beta_evidence=private_beta_evidence,
            release_notes=release_notes,
            release_version="v0.1.0-private-beta",
        )
    )

    mobile_check = next(check for check in result["checks"] if check["name"] == "mobile-release-evidence")
    assert result["ready"] is False
    assert result["missingArtifacts"] == []
    assert result["failedChecks"] == ["mobile-release-evidence"]
    assert mobile_check["details"]["failedChecks"] == ["ios-signed-build"]


def test_release_packet_status_accepts_complete_local_packet(tmp_path):
    metadata = tmp_path / "metadata.json"
    mail_store = tmp_path / "mail-store.tar.gz"
    mobile_evidence = tmp_path / "mobile-release-evidence.json"
    restore_drill = tmp_path / "restore-drill-evidence.json"
    mobile_app_config = tmp_path / "app.json"
    private_beta_evidence = tmp_path / "private-beta-gate.json"
    release_notes = tmp_path / "release-notes.md"
    metadata.write_text("{}", encoding="utf-8")
    mail_store.write_bytes(b"archive")
    write_json(restore_drill, valid_restore_drill_evidence())
    write_json(mobile_app_config, valid_mobile_app_config())
    write_json(mobile_evidence, valid_mobile_release_evidence())
    write_json(private_beta_evidence, valid_private_beta_evidence())
    write_release_notes(release_notes)

    result = summarize_release_packet(
        ReleasePacketStatusOptions(
            metadata_backup=metadata,
            mail_store_backup=mail_store,
            restore_drill_evidence=restore_drill,
            mobile_release_evidence=mobile_evidence,
            mobile_app_config=mobile_app_config,
            private_beta_evidence=private_beta_evidence,
            release_notes=release_notes,
            release_version="v0.1.0-private-beta",
            require_mobile_store_submission=True,
        )
    )

    artifacts = {artifact["flag"]: artifact for artifact in result["artifacts"]}
    assert result["ready"] is True
    assert result["failedChecks"] == []
    assert artifacts["--metadata-backup"]["sha256"] == hashlib.sha256(b"{}").hexdigest()
    assert artifacts["--mail-store-backup"]["sha256"] == hashlib.sha256(b"archive").hexdigest()
    assert artifacts["--restore-drill-evidence"]["sha256"] == hashlib.sha256(
        restore_drill.read_bytes()
    ).hexdigest()


def test_release_packet_status_script_exits_nonzero_until_packet_ready(tmp_path):
    completed = subprocess.run(
        [sys.executable, "scripts/release_packet_status.py", "--metadata-backup", str(tmp_path / "missing.json")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ready"] is False
    assert "--metadata-backup" in payload["missingArtifacts"]


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


def write_release_notes(path):
    path.write_text(
        "# FreeMail v0.1.0-private-beta\n\n"
        "Verification: CI, release gates, and backup evidence passed.\n\n"
        "Known limitations: VPN-only private beta.\n",
        encoding="utf-8",
    )


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
