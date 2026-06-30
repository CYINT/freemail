import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mobile_device_validation import (  # noqa: E402
    MobileDeviceValidationOptions,
    REQUIRED_DEVICE_CHECKS,
    collect_mobile_device_validation,
)
from freemail_api.mobile_release_evidence import MOBILE_EVIDENCE_FILENAME  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Record credential-free FreeMail mobile device validation evidence.")
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path(".freemail-qa") / MOBILE_EVIDENCE_FILENAME,
        help="Existing mobile release evidence JSON to update.",
    )
    parser.add_argument("--platform", choices=["ios", "android"], required=True)
    parser.add_argument("--tester", required=True, help="Non-secret tester label.")
    parser.add_argument("--device-model", required=True)
    parser.add_argument("--os-version", required=True)
    parser.add_argument("--evidence-url", required=True, help="HTTPS URL to credential-free validation evidence.")
    parser.add_argument("--tested", action="store_true", help="Explicitly record that the platform was tested.")
    parser.add_argument("--tested-at", help="Timezone-aware ISO-8601 timestamp. Defaults to current UTC time.")
    parser.add_argument("--app-version", help="Defaults to the app.version recorded in the mobile evidence file.")
    parser.add_argument("--hostname", default="freemail.kuzuryu.ai")
    parser.add_argument("--network-boundary", default="Dragonscale/VPN clients only")
    parser.add_argument(
        "--passed-check",
        choices=REQUIRED_DEVICE_CHECKS,
        action="append",
        default=[],
        help="Required device check that passed. Repeat for each passing check.",
    )
    parser.add_argument(
        "--failed-check",
        choices=REQUIRED_DEVICE_CHECKS,
        action="append",
        default=[],
        help="Required device check that failed. Repeat for each failing check.",
    )
    parser.add_argument(
        "--all-checks-passed",
        action="store_true",
        help="Convenience flag equivalent to passing every required device check.",
    )
    args = parser.parse_args()

    passed_checks = tuple(REQUIRED_DEVICE_CHECKS if args.all_checks_passed else args.passed_check)
    result = collect_mobile_device_validation(
        MobileDeviceValidationOptions(
            evidence=args.evidence,
            platform=args.platform,
            tester=args.tester,
            device_model=args.device_model,
            os_version=args.os_version,
            evidence_url=args.evidence_url,
            tested=args.tested,
            tested_at=_parse_timestamp(args.tested_at),
            app_version=args.app_version,
            hostname=args.hostname,
            network_boundary=args.network_boundary,
            passed_checks=passed_checks,
            failed_checks=tuple(args.failed_check),
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["platformReady"] else 2


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


if __name__ == "__main__":
    sys.exit(main())
