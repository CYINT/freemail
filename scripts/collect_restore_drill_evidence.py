import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mail_store_backup import DEFAULT_DOCKER_IMAGE  # noqa: E402
from freemail_api.restore_drill_evidence import (  # noqa: E402
    DEFAULT_DRILL_VOLUME,
    RestoreDrillEvidenceOptions,
    collect_restore_drill_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect FreeMail restore-drill evidence from backup artifacts.")
    parser.add_argument("--metadata-backup", type=Path, required=True, help="Metadata backup JSON to restore.")
    parser.add_argument("--mail-store-backup", type=Path, required=True, help="Mail-store tar.gz archive to restore.")
    parser.add_argument("--output", type=Path, required=True, help="Credential-free restore-drill evidence JSON path.")
    parser.add_argument("--drill-database", type=Path, required=True, help="SQLite path for the restored drill database.")
    parser.add_argument("--drill-mail-store-volume", default=DEFAULT_DRILL_VOLUME, help="Dedicated Docker drill volume.")
    parser.add_argument("--image", default=DEFAULT_DOCKER_IMAGE, help="Helper container image.")
    parser.add_argument("--force", action="store_true", help="Replace existing drill database and evidence output.")
    args = parser.parse_args()

    result = collect_restore_drill_evidence(
        RestoreDrillEvidenceOptions(
            metadata_backup=args.metadata_backup,
            mail_store_backup=args.mail_store_backup,
            output=args.output,
            drill_database=args.drill_database,
            drill_mail_store_volume=args.drill_mail_store_volume,
            image=args.image,
            force=args.force,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
