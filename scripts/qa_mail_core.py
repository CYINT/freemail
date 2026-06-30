import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mail_core import probe_mail_core
from freemail_api.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe FreeMail mail-core protocol readiness.")
    parser.add_argument("--strict", action="store_true", help="Fail unless SMTP, submission, IMAP, and JMAP are ready.")
    args = parser.parse_args()

    settings = get_settings()
    result = probe_mail_core(
        host=settings.mail_core_host,
        smtp_port=settings.smtp_port,
        submission_port=settings.submission_port,
        imap_port=settings.imap_port,
        jmap_port=settings.jmap_port,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.strict and not result["protocolReady"]:
        return 1
    if not result["tcpReachable"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
