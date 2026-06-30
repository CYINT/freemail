import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.settings import get_settings
from freemail_api.stalwart_plan import MissingProvisioningSecretError, PlanOptions, build_apply_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a Stalwart apply-plan NDJSON file from FreeMail metadata.")
    parser.add_argument("--database", help="Path to the FreeMail SQLite metadata database.")
    parser.add_argument("--secrets-json", help="Ignored JSON file mapping mailbox email addresses to mail-core secrets.")
    parser.add_argument("--skip-users-without-secret", action="store_true")
    args = parser.parse_args()

    database_path = args.database or get_settings().database_path
    user_secrets = _load_user_secrets(args.secrets_json)
    try:
        with sqlite3.connect(database_path) as connection:
            plan = build_apply_plan(
                connection,
                PlanOptions(
                    user_secrets=user_secrets,
                    skip_users_without_secret=args.skip_users_without_secret,
                ),
            )
    except MissingProvisioningSecretError as error:
        print(str(error), file=sys.stderr)
        return 2

    for operation in plan:
        print(json.dumps(operation, sort_keys=True))
    return 0


def _load_user_secrets(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    with Path(path).open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("secrets JSON must be an object mapping email addresses to secrets")
    return {str(key).lower(): str(value) for key, value in data.items()}


if __name__ == "__main__":
    sys.exit(main())
