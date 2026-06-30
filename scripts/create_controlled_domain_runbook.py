import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.controlled_domain_runbook import (  # noqa: E402
    ControlledDomainRunbookOptions,
    create_controlled_domain_runbook,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a credential-free FreeMail controlled-domain release runbook.")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=Path("data/freemail.sqlite"))
    parser.add_argument("--admin-email")
    parser.add_argument("--admin-display-name", default="FreeMail Administrator")
    parser.add_argument("--admin-password-env", default="FREEMAIL_PRIVATE_BETA_ADMIN_PASSWORD")
    parser.add_argument("--hostname", default="freemail.kuzuryu.ai")
    parser.add_argument("--secrets-json", type=Path, default=Path("secrets/mail-core-users.json"))
    parser.add_argument("--release-version", default="v0.1.0-private-beta")
    parser.add_argument("--release-notes", type=Path, default=Path("docs/release-notes/v0.1.0-private-beta.md"))
    parser.add_argument("--mobile-release-evidence", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--write-markdown", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = create_controlled_domain_runbook(
        ControlledDomainRunbookOptions(
            domain=args.domain,
            output=args.output,
            evidence_dir=args.evidence_dir,
            database=args.database,
            admin_email=args.admin_email,
            admin_display_name=args.admin_display_name,
            admin_password_env=args.admin_password_env,
            hostname=args.hostname,
            secrets_json=args.secrets_json,
            release_version=args.release_version,
            release_notes=args.release_notes,
            mobile_release_evidence=args.mobile_release_evidence,
            backup_dir=args.backup_dir,
            write_markdown=args.write_markdown,
            force=args.force,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
