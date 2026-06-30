import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.private_beta_gate import PrivateBetaGateOptions, run_private_beta_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Run FreeMail private-beta readiness gates.")
    parser.add_argument("--domain")
    parser.add_argument("--dns-guidance", type=Path)
    parser.add_argument("--observed-dns", type=Path)
    parser.add_argument("--mail-flow-evidence", type=Path)
    parser.add_argument("--queue-evidence", type=Path)
    parser.add_argument("--mail-core-apply-evidence", type=Path)
    parser.add_argument("--deliverability-evidence", type=Path)
    parser.add_argument("--metadata-backup", type=Path)
    parser.add_argument("--mail-store-backup", type=Path)
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--skip-dns", action="store_true")
    parser.add_argument("--skip-evidence", action="store_true")
    parser.add_argument("--health-url", default="https://freemail.kuzuryu.ai/health")
    parser.add_argument("--deployment-url", default="https://freemail.kuzuryu.ai/api/v1/deployment")
    parser.add_argument("--metadata-readiness-url", default="https://freemail.kuzuryu.ai/api/v1/metadata/readiness")
    parser.add_argument("--readiness-url", default="https://freemail.kuzuryu.ai/api/v1/mail-core/readiness")
    parser.add_argument("--skip-runtime", action="store_true")
    args = parser.parse_args()

    result = run_private_beta_gate(
        PrivateBetaGateOptions(
            domain=args.domain,
            dns_guidance=args.dns_guidance,
            observed_dns=args.observed_dns,
            mail_flow_evidence=args.mail_flow_evidence,
            queue_evidence=args.queue_evidence,
            mail_core_apply_evidence=args.mail_core_apply_evidence,
            deliverability_evidence=args.deliverability_evidence,
            metadata_backup=args.metadata_backup,
            mail_store_backup=args.mail_store_backup,
            acceptance=args.acceptance,
            skip_dns=args.skip_dns,
            skip_evidence=args.skip_evidence,
            health_url=args.health_url,
            deployment_url=args.deployment_url,
            metadata_readiness_url=args.metadata_readiness_url,
            readiness_url=args.readiness_url,
            skip_runtime=args.skip_runtime,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
