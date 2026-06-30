import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from freemail_api.open_source_readiness import (  # noqa: E402
    OpenSourceReadinessOptions,
    check_open_source_readiness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FreeMail open-source publication readiness.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    payload = check_open_source_readiness(OpenSourceReadinessOptions(root=args.root))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
