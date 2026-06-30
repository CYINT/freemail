import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api import database
from freemail_api.backup import BackupError, restore_metadata_backup
from freemail_api.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a FreeMail API metadata JSON backup.")
    parser.add_argument("--database", help="Path to the FreeMail SQLite metadata database.")
    parser.add_argument("--input", required=True, help="Input JSON backup path.")
    parser.add_argument("--force", action="store_true", help="Replace existing metadata in the target database.")
    args = parser.parse_args()

    database_path = args.database or get_settings().database_path
    database.initialize(database_path)

    with Path(args.input).open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)

    try:
        with database.connect(database_path) as connection:
            restore_metadata_backup(connection, payload, force=args.force)
    except BackupError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
