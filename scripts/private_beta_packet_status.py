import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.private_beta_evidence import summarize_private_beta_evidence_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a FreeMail private-beta evidence packet manifest.")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    result = summarize_private_beta_evidence_manifest(args.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
