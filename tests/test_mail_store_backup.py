from pathlib import Path
import subprocess

import pytest

from freemail_api.mail_store_backup import (
    MailStoreBackupError,
    build_backup_command,
    build_restore_commands,
    run_mail_store_backup,
    run_mail_store_restore,
)


def test_build_backup_command_archives_volume_through_helper_container(tmp_path):
    output = tmp_path / "backups" / "mail-store.tar.gz"

    command = build_backup_command(volume="freemail_freemail_stalwart", output=output, image="alpine:test")

    assert command[:3] == ["docker", "run", "--rm"]
    assert "-v" in command
    assert "freemail_freemail_stalwart:/source:ro" in command
    assert f"{output.resolve().parent}:/backup" in command
    assert command[-6:] == ["tar", "-C", "/source", "-czf", "/backup/mail-store.tar.gz", "."]


def test_build_restore_commands_create_clear_and_extract_volume(tmp_path):
    backup = tmp_path / "mail-store.tar.gz"
    backup.write_bytes(b"not-a-real-archive")

    commands = build_restore_commands(volume="freemail_stalwart_restore", backup=backup, image="alpine:test")

    assert commands[0] == ["docker", "volume", "create", "freemail_stalwart_restore"]
    assert commands[1][:4] == ["docker", "run", "--rm", "-v"]
    assert "freemail_stalwart_restore:/target" in commands[1]
    assert commands[1][-11:] == [
        "find",
        "/target",
        "-mindepth",
        "1",
        "-maxdepth",
        "1",
        "-exec",
        "rm",
        "-rf",
        "{}",
        ";",
    ]
    assert commands[2][-5:] == ["tar", "-C", "/target", "-xzf", "/backup/mail-store.tar.gz"]


def test_run_mail_store_backup_creates_parent_and_runs_docker(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, check):
        calls.append((command, check))

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = tmp_path / "nested" / "mail-store.tar.gz"

    run_mail_store_backup(volume="freemail_freemail_stalwart", output=output, image="alpine:test")

    assert output.parent.is_dir()
    assert calls[0][1] is True
    assert calls[0][0][0:3] == ["docker", "run", "--rm"]


def test_run_mail_store_restore_requires_force(tmp_path):
    backup = tmp_path / "mail-store.tar.gz"
    backup.write_bytes(b"not-a-real-archive")

    with pytest.raises(MailStoreBackupError, match="requires --force"):
        run_mail_store_restore(volume="freemail_stalwart_restore", backup=backup, force=False)


def test_run_mail_store_restore_runs_docker_steps(tmp_path, monkeypatch):
    calls = []
    backup = tmp_path / "mail-store.tar.gz"
    backup.write_bytes(b"not-a-real-archive")

    def fake_run(command, check):
        calls.append((command, check))

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_mail_store_restore(volume="freemail_stalwart_restore", backup=backup, image="alpine:test", force=True)

    assert [call[0][0:2] for call in calls] == [["docker", "volume"], ["docker", "run"], ["docker", "run"]]
    assert all(call[1] is True for call in calls)


def test_volume_name_validation_rejects_shell_metacharacters(tmp_path):
    with pytest.raises(MailStoreBackupError, match="volume name"):
        build_backup_command(volume="freemail_freemail_stalwart;rm", output=Path(tmp_path / "backup.tar.gz"))
