import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.deliverability_evidence import DeliverabilityEvidenceOptions, collect_deliverability_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create credential-free FreeMail deliverability evidence from mail-flow and queue evidence."
    )
    parser.add_argument("--domain", required=True)
    parser.add_argument("--mail-flow-evidence", type=Path, required=True)
    parser.add_argument("--queue-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spf-aligned", action="store_true")
    parser.add_argument("--dmarc-aligned", action="store_true")
    parser.add_argument("--bounce-or-retry-reviewed", action="store_true")
    parser.add_argument("--abuse-complaints", type=int, default=-1)
    parser.add_argument("--checked-at", help="Timezone-aware ISO-8601 timestamp. Defaults to current UTC time.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    payload = collect_deliverability_evidence(
        DeliverabilityEvidenceOptions(
            domain=args.domain,
            mail_flow_evidence=args.mail_flow_evidence,
            queue_evidence=args.queue_evidence,
            output=args.output,
            spf_aligned=args.spf_aligned,
            dmarc_aligned=args.dmarc_aligned,
            bounce_or_retry_reviewed=args.bounce_or_retry_reviewed,
            abuse_complaints=args.abuse_complaints,
            checked_at=_parse_timestamp(args.checked_at),
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
