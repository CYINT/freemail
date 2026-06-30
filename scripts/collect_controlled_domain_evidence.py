import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.controlled_domain_evidence import (  # noqa: E402
    ControlledDomainEvidenceOptions,
    collect_controlled_domain_evidence,
    load_mailbox_password,
)
from freemail_api.settings import get_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect credential-free FreeMail controlled-domain evidence.")
    parser.add_argument("--domain", required=True, help="Controlled beta domain, for example example.com.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for private-beta evidence files.")
    parser.add_argument("--email", required=True, help="Mailbox login email used for controlled mail-flow checks.")
    parser.add_argument("--password", help="Mailbox password. Prefer --secrets-json for local runs.")
    parser.add_argument("--secrets-json", type=Path, help="Ignored JSON mapping mailbox email addresses to passwords.")
    parser.add_argument("--dns-guidance", type=Path, help="Admin DNS guidance JSON to resolve into observed DNS evidence.")
    parser.add_argument("--inbound-recipient", help="SMTP recipient to test inbound delivery.")
    parser.add_argument("--inbound-sender", default="sender@example.net", help="SMTP sender for inbound delivery.")
    parser.add_argument("--submission-recipient", help="Recipient for authenticated submission smoke.")
    parser.add_argument("--require-dkim-domain", help="Required DKIM d= domain. Defaults to --domain.")
    parser.add_argument("--spf-aligned", action="store_true", help="Operator-reviewed SPF alignment passed.")
    parser.add_argument("--dmarc-aligned", action="store_true", help="Operator-reviewed DMARC alignment passed.")
    parser.add_argument("--bounce-or-retry-reviewed", action="store_true", help="Operator reviewed bounce/retry state.")
    parser.add_argument("--abuse-complaints", type=int, default=-1, help="Known abuse complaint count; use 0 to pass.")
    parser.add_argument("--decision-owner", default="", help="Optional decision owner for the acceptance draft.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated evidence files.")
    parser.add_argument("--verify-tls", action="store_true", help="Verify TLS certificates for mail protocols.")
    parser.add_argument("--poll-attempts", type=int, default=10)
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--queue-image", default="ghcr.io/stalwartlabs/cli")
    parser.add_argument("--queue-timeout-seconds", type=int, default=30)
    args = parser.parse_args()

    password = args.password or load_mailbox_password(args.secrets_json, args.email)
    result = collect_controlled_domain_evidence(
        ControlledDomainEvidenceOptions(
            domain=args.domain,
            output_dir=args.output_dir,
            email=args.email,
            password=password,
            settings=get_settings(),
            dns_guidance=args.dns_guidance,
            inbound_recipient=args.inbound_recipient,
            inbound_sender=args.inbound_sender,
            submission_recipient=args.submission_recipient,
            require_dkim_domain=args.require_dkim_domain,
            spf_aligned=args.spf_aligned,
            dmarc_aligned=args.dmarc_aligned,
            bounce_or_retry_reviewed=args.bounce_or_retry_reviewed,
            abuse_complaints=args.abuse_complaints,
            decision_owner=args.decision_owner,
            force=args.force,
            verify_tls=args.verify_tls,
            poll_attempts=args.poll_attempts,
            poll_interval_seconds=args.poll_interval_seconds,
            queue_image=args.queue_image,
            queue_timeout_seconds=args.queue_timeout_seconds,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["collected"]["mailFlow"] and result["collected"]["queueClear"] else 1


if __name__ == "__main__":
    sys.exit(main())
