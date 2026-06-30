import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.settings import get_settings  # noqa: E402
from freemail_api.stalwart_apply_evidence import (  # noqa: E402
    StalwartApplyEvidenceOptions,
    collect_stalwart_apply_evidence,
    load_user_secrets,
    write_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Stalwart apply and write credential-free FreeMail mail-core apply evidence."
    )
    parser.add_argument("--domain", required=True, help="Controlled beta domain the apply run provisions.")
    parser.add_argument("--database", help="Path to the FreeMail SQLite metadata database.")
    parser.add_argument("--secrets-json", type=Path, required=True, help="Ignored email-to-mail-core-secret JSON file.")
    parser.add_argument("--output", type=Path, required=True, help="Credential-free evidence JSON output path.")
    parser.add_argument("--applied-by", default=os.environ.get("USERNAME") or os.environ.get("USER") or "")
    parser.add_argument("--image", default="ghcr.io/stalwartlabs/cli")
    parser.add_argument("--queue-image", default="ghcr.io/stalwartlabs/cli")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()

    settings = get_settings()
    user_secrets = load_user_secrets(args.secrets_json)
    database_path = args.database or settings.database_path
    with sqlite3.connect(database_path) as connection:
        evidence = collect_stalwart_apply_evidence(
            connection,
            StalwartApplyEvidenceOptions(
                domain=args.domain,
                user_secrets=user_secrets,
                applied_by=args.applied_by,
                image=args.image,
                queue_image=args.queue_image,
                timeout_seconds=args.timeout_seconds,
                mail_core_host=settings.mail_core_host,
                smtp_port=settings.smtp_port,
                submission_port=settings.submission_port,
                imap_port=settings.imap_port,
                jmap_port=settings.jmap_port,
            ),
        )
    write_evidence(args.output, evidence)
    print(json.dumps({"output": str(args.output), "applied": evidence["applied"]}, indent=2, sort_keys=True))
    return 0 if evidence["applied"] and evidence["postApplyReadiness"]["mailCoreReady"] else 1


if __name__ == "__main__":
    sys.exit(main())
