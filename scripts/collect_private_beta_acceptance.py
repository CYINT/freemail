import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.private_beta_acceptance import (  # noqa: E402
    DEFAULT_KNOWN_LIMITATIONS,
    PrivateBetaAcceptanceOptions,
    collect_private_beta_acceptance,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create credential-free FreeMail private-beta acceptance evidence.")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decision-owner", required=True)
    parser.add_argument("--accepted", action="store_true", help="Explicitly record decision-owner acceptance.")
    parser.add_argument("--accepted-at", help="Timezone-aware ISO-8601 timestamp. Defaults to current UTC time.")
    parser.add_argument("--access-boundary", default="Dragonscale/VPN clients only")
    parser.add_argument(
        "--known-limitation",
        action="append",
        dest="known_limitations",
        help="Known private-beta limitation. Can be provided more than once.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    payload = collect_private_beta_acceptance(
        PrivateBetaAcceptanceOptions(
            domain=args.domain,
            output=args.output,
            decision_owner=args.decision_owner,
            accepted=args.accepted,
            accepted_at=_parse_timestamp(args.accepted_at),
            access_boundary=args.access_boundary,
            known_limitations=tuple(args.known_limitations or DEFAULT_KNOWN_LIMITATIONS),
            force=args.force,
        )
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 2


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


if __name__ == "__main__":
    sys.exit(main())
