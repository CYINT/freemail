import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.release_evidence import ReleaseEvidenceManifestOptions, create_release_evidence_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a FreeMail release evidence manifest.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata-backup", type=Path)
    parser.add_argument("--mail-store-backup", type=Path)
    parser.add_argument("--mobile-release-evidence", type=Path)
    parser.add_argument("--mobile-app-config", type=Path, default=Path("apps/mobile/app.json"))
    parser.add_argument("--private-beta-evidence", type=Path)
    parser.add_argument("--release-notes", type=Path)
    parser.add_argument("--release-version")
    parser.add_argument("--require-mobile-store-submission", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = create_release_evidence_manifest(
        ReleaseEvidenceManifestOptions(
            output=args.output,
            metadata_backup=args.metadata_backup,
            mail_store_backup=args.mail_store_backup,
            mobile_release_evidence=args.mobile_release_evidence,
            mobile_app_config=args.mobile_app_config,
            private_beta_evidence=args.private_beta_evidence,
            release_notes=args.release_notes,
            release_version=args.release_version,
            require_mobile_store_submission=args.require_mobile_store_submission,
            force=args.force,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
