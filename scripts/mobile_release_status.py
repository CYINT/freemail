import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mobile_release_evidence import MOBILE_EVIDENCE_FILENAME  # noqa: E402
from freemail_api.mobile_release_status import summarize_mobile_release_evidence  # noqa: E402


DEFAULT_MOBILE_RELEASE_EVIDENCE_CANDIDATES = (
    Path(".freemail-qa/mobile-release-evidence.freemail.kuzuryu.ai.json"),
    Path(".freemail-qa") / MOBILE_EVIDENCE_FILENAME,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect FreeMail mobile release evidence without signing tools.")
    parser.add_argument(
        "--evidence",
        type=Path,
        help="Credential-free mobile release evidence JSON.",
    )
    parser.add_argument("--app-config", type=Path, default=Path("apps/mobile/app.json"))
    parser.add_argument("--require-store-submission", action="store_true")
    args = parser.parse_args()

    result = summarize_mobile_release_evidence(
        evidence=args.evidence or _default_mobile_release_evidence(),
        app_config=args.app_config,
        require_store_submission=args.require_store_submission,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready"] else 1


def _default_mobile_release_evidence() -> Path:
    return next(
        (path for path in DEFAULT_MOBILE_RELEASE_EVIDENCE_CANDIDATES if path.exists()),
        DEFAULT_MOBILE_RELEASE_EVIDENCE_CANDIDATES[-1],
    )


if __name__ == "__main__":
    sys.exit(main())
