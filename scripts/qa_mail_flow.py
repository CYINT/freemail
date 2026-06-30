import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mail_flow_smoke import run_mail_flow_smoke
from freemail_api.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Send and retrieve FreeMail smoke messages.")
    parser.add_argument("--email", required=True, help="Mailbox login email.")
    parser.add_argument("--password", help="Mailbox password. Prefer --secrets-json for local runs.")
    parser.add_argument("--secrets-json", help="Ignored JSON mapping email addresses to mailbox passwords.")
    parser.add_argument("--inbound-recipient", help="SMTP recipient to test inbound delivery.")
    parser.add_argument("--inbound-sender", default="sender@example.net", help="SMTP sender for inbound delivery.")
    parser.add_argument("--submission-recipient", help="Recipient for authenticated submission smoke.")
    parser.add_argument("--poll-attempts", type=int, default=10)
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--verify-tls", action="store_true", help="Verify TLS certificates.")
    args = parser.parse_args()

    password = args.password or _load_password(args.secrets_json, args.email)
    settings = get_settings()
    result = run_mail_flow_smoke(
        email=args.email,
        password=password,
        host=settings.mail_core_host,
        smtp_port=settings.smtp_port,
        submission_port=settings.submission_port,
        imap_port=settings.imap_port,
        inbound_recipient=args.inbound_recipient or args.email,
        inbound_sender=args.inbound_sender,
        submission_recipient=args.submission_recipient or args.email,
        poll_attempts=args.poll_attempts,
        poll_interval_seconds=args.poll_interval_seconds,
        verify_tls=args.verify_tls,
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.passed else 1


def _load_password(path: str | None, email: str) -> str:
    if not path:
        raise ValueError("Provide --password or --secrets-json")
    with Path(path).open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("secrets JSON must be an object mapping email addresses to passwords")
    try:
        return str(data[email.lower()])
    except KeyError as error:
        raise ValueError(f"Missing password for {email}") from error


if __name__ == "__main__":
    sys.exit(main())
