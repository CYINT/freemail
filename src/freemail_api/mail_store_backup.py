from __future__ import annotations

from pathlib import Path
import subprocess


DEFAULT_DOCKER_IMAGE = "alpine:3.20"
DEFAULT_VOLUME = "freemail_freemail_stalwart"


class MailStoreBackupError(ValueError):
    pass


def run_mail_store_backup(
    *,
    volume: str,
    output: Path,
    image: str = DEFAULT_DOCKER_IMAGE,
) -> None:
    _validate_volume_name(volume)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = build_backup_command(volume=volume, output=output, image=image)
    subprocess.run(command, check=True)


def run_mail_store_restore(
    *,
    volume: str,
    backup: Path,
    image: str = DEFAULT_DOCKER_IMAGE,
    force: bool,
) -> None:
    if not force:
        raise MailStoreBackupError("mail-store restore requires --force")
    _validate_volume_name(volume)
    if not backup.is_file():
        raise MailStoreBackupError(f"backup file does not exist: {backup}")
    for command in build_restore_commands(volume=volume, backup=backup, image=image):
        subprocess.run(command, check=True)


def build_backup_command(*, volume: str, output: Path, image: str = DEFAULT_DOCKER_IMAGE) -> list[str]:
    _validate_volume_name(volume)
    output_path = output.resolve()
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{volume}:/source:ro",
        "-v",
        f"{output_path.parent}:/backup",
        image,
        "tar",
        "-C",
        "/source",
        "-czf",
        f"/backup/{output_path.name}",
        ".",
    ]


def build_restore_commands(*, volume: str, backup: Path, image: str = DEFAULT_DOCKER_IMAGE) -> list[list[str]]:
    _validate_volume_name(volume)
    backup_path = backup.resolve()
    return [
        ["docker", "volume", "create", volume],
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/target",
            image,
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
        ],
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/target",
            "-v",
            f"{backup_path.parent}:/backup:ro",
            image,
            "tar",
            "-C",
            "/target",
            "-xzf",
            f"/backup/{backup_path.name}",
        ],
    ]


def _validate_volume_name(volume: str) -> None:
    if not volume:
        raise MailStoreBackupError("volume name is required")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
    if any(character not in allowed for character in volume):
        raise MailStoreBackupError("volume name may only contain letters, numbers, dot, underscore, or dash")
