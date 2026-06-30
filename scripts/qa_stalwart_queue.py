import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.stalwart_queue import query_queue_with_cli


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Stalwart queued messages through the official CLI container.")
    parser.add_argument("--image", default="ghcr.io/stalwartlabs/cli")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--allow-pending", action="store_true", help="Return success even if queued messages are pending.")
    args = parser.parse_args()

    summary = query_queue_with_cli(image=args.image, timeout_seconds=args.timeout_seconds)
    print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    return 0 if summary.clear or args.allow_pending else 1


if __name__ == "__main__":
    sys.exit(main())
