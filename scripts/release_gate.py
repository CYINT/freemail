import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.release_gate import assert_release_gate, ReleaseGateError, ReleaseGateOptions


def main() -> int:
    parser = argparse.ArgumentParser(description="Run FreeMail local release gates for the current commit.")
    parser.add_argument("--repo", default="CYINT/freemail")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--health-url", default="https://freemail.kuzuryu.ai/health")
    parser.add_argument("--deployment-url", default="https://freemail.kuzuryu.ai/api/v1/deployment")
    parser.add_argument("--metadata-readiness-url", default="https://freemail.kuzuryu.ai/api/v1/metadata/readiness")
    parser.add_argument("--readiness-url", default="https://freemail.kuzuryu.ai/api/v1/mail-core/readiness")
    parser.add_argument("--metadata-backup", type=Path)
    parser.add_argument("--mail-store-backup", type=Path)
    parser.add_argument("--skip-github-ci", action="store_true")
    parser.add_argument("--skip-backup-evidence", action="store_true")
    parser.add_argument("--skip-runtime", action="store_true")
    args = parser.parse_args()

    options = ReleaseGateOptions(
        repo=args.repo,
        remote=args.remote,
        branch=args.branch,
        health_url=args.health_url,
        deployment_url=args.deployment_url,
        metadata_readiness_url=args.metadata_readiness_url,
        readiness_url=args.readiness_url,
        metadata_backup=args.metadata_backup,
        mail_store_backup=args.mail_store_backup,
        skip_github_ci=args.skip_github_ci,
        skip_backup_evidence=args.skip_backup_evidence,
        skip_runtime=args.skip_runtime,
    )
    try:
        result = assert_release_gate(options)
    except ReleaseGateError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
