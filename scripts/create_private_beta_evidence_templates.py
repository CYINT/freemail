import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.private_beta_evidence import (  # noqa: E402
    PrivateBetaEvidenceTemplateOptions,
    create_private_beta_evidence_templates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create draft FreeMail private-beta evidence JSON templates.")
    parser.add_argument("--domain", required=True, help="Controlled beta domain, for example example.com.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated evidence templates.")
    parser.add_argument("--decision-owner", default="", help="Optional decision-owner name for acceptance draft.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing draft template files.")
    args = parser.parse_args()

    result = create_private_beta_evidence_templates(
        PrivateBetaEvidenceTemplateOptions(
            domain=args.domain,
            output_dir=args.output_dir,
            decision_owner=args.decision_owner,
            force=args.force,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
