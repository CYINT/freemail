import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.backup_evidence import BackupEvidenceOptions, collect_backup_evidence  # noqa: E402
from freemail_api.mail_store_backup import DEFAULT_DOCKER_IMAGE, DEFAULT_VOLUME  # noqa: E402
from freemail_api.settings import get_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect FreeMail metadata and mail-store backup evidence.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated backup artifacts.")
    parser.add_argument("--database", help="Path to the FreeMail SQLite metadata database.")
    parser.add_argument("--mail-store-volume", default=DEFAULT_VOLUME, help="Docker volume to archive.")
    parser.add_argument("--image", default=DEFAULT_DOCKER_IMAGE, help="Helper container image.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing backup evidence artifacts.")
    args = parser.parse_args()

    result = collect_backup_evidence(
        BackupEvidenceOptions(
            output_dir=args.output_dir,
            database_path=args.database or get_settings().database_path,
            mail_store_volume=args.mail_store_volume,
            image=args.image,
            force=args.force,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
