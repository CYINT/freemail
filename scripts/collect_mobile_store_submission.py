import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mobile_release_collectors import (  # noqa: E402
    MobileStoreSubmissionOptions,
    collect_mobile_store_submission,
)
from freemail_api.mobile_release_evidence import MOBILE_EVIDENCE_FILENAME  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Record credential-free FreeMail mobile store-submission evidence.")
    parser.add_argument("--evidence", type=Path, default=Path(".freemail-qa") / MOBILE_EVIDENCE_FILENAME)
    parser.add_argument("--platform", choices=["ios", "android"], required=True)
    parser.add_argument("--submitted", action="store_true", help="Explicitly record that this submission was made.")
    parser.add_argument("--track", required=True)
    parser.add_argument("--submission-url", required=True, help="HTTPS URL to credential-free store-submission evidence.")
    parser.add_argument("--submitted-at", required=True, help="Timezone-aware ISO-8601 timestamp.")
    parser.add_argument("--review-state", required=True)
    args = parser.parse_args()

    result = collect_mobile_store_submission(
        MobileStoreSubmissionOptions(
            evidence=args.evidence,
            platform=args.platform,
            submitted=args.submitted,
            track=args.track,
            submission_url=args.submission_url,
            submitted_at=_parse_timestamp(args.submitted_at),
            review_state=args.review_state,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["platformReady"] else 2


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


if __name__ == "__main__":
    sys.exit(main())
