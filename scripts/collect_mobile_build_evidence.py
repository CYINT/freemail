import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mobile_release_collectors import MobileBuildEvidenceOptions, collect_mobile_build_evidence  # noqa: E402
from freemail_api.mobile_release_evidence import MOBILE_EVIDENCE_FILENAME  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Record credential-free FreeMail signed mobile build evidence.")
    parser.add_argument("--evidence", type=Path, default=Path(".freemail-qa") / MOBILE_EVIDENCE_FILENAME)
    parser.add_argument("--platform", choices=["ios", "android"], required=True)
    parser.add_argument("--signed", action="store_true", help="Explicitly record that this build is signed.")
    parser.add_argument("--distribution", default="private-beta")
    parser.add_argument("--build-url", required=True, help="HTTPS URL to credential-free build provenance.")
    parser.add_argument("--native-build-id", required=True, help="iOS buildNumber or Android versionCode used for this artifact.")
    parser.add_argument("--artifact-type", required=True, help="ipa for iOS; aab or apk for Android.")
    parser.add_argument("--artifact-bytes", type=int, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    args = parser.parse_args()

    result = collect_mobile_build_evidence(
        MobileBuildEvidenceOptions(
            evidence=args.evidence,
            platform=args.platform,
            signed=args.signed,
            distribution=args.distribution,
            build_url=args.build_url,
            native_build_id=args.native_build_id,
            artifact_type=args.artifact_type,
            artifact_bytes=args.artifact_bytes,
            artifact_sha256=args.artifact_sha256,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["platformReady"] else 2


if __name__ == "__main__":
    sys.exit(main())
