import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mobile_release_evidence import (  # noqa: E402
    MobileReleaseEvidenceTemplateOptions,
    create_mobile_release_evidence_template,
    default_mobile_release_evidence_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a draft FreeMail mobile release evidence JSON template.")
    parser.add_argument(
        "--output",
        type=Path,
        default=default_mobile_release_evidence_path(),
        help="Path for the generated mobile release evidence template.",
    )
    parser.add_argument("--app-config", type=Path, default=Path("apps/mobile/app.json"))
    parser.add_argument("--force", action="store_true", help="Overwrite an existing draft template file.")
    args = parser.parse_args()

    result = create_mobile_release_evidence_template(
        MobileReleaseEvidenceTemplateOptions(output=args.output, app_config=args.app_config, force=args.force)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
