import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api import database
from freemail_api.backup import export_metadata_backup
from freemail_api.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Export FreeMail API metadata as a JSON backup.")
    parser.add_argument("--database", help="Path to the FreeMail SQLite metadata database.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    args = parser.parse_args()

    database_path = args.database or get_settings().database_path
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with database.connect(database_path) as connection:
        payload = export_metadata_backup(connection)

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
