import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate FreeMail mobile signed-build release evidence.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--app-config", type=Path, default=Path("apps/mobile/app.json"))
    args = parser.parse_args()

    result = run_mobile_release_gate(MobileReleaseGateOptions(evidence=args.evidence, app_config=args.app_config))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
