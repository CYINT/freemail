import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.controlled_domain_provisioning import (  # noqa: E402
    ControlledDomainProvisioningOptions,
    provision_controlled_domain,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision FreeMail metadata for a controlled private-beta domain.")
    parser.add_argument("--database", type=Path, default=Path("data/freemail.sqlite"))
    parser.add_argument("--domain", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-display-name", default="FreeMail Administrator")
    parser.add_argument("--admin-initial-password-env", help="Environment variable containing the initial admin password.")
    parser.add_argument("--mailbox-local-part")
    parser.add_argument("--dkim-selector", default="mail")
    parser.add_argument("--hostname", default="freemail.kuzuryu.ai")
    parser.add_argument("--secrets-json", type=Path, default=Path("secrets/mail-core-users.json"))
    parser.add_argument("--force-secret", action="store_true", help="Overwrite the local ignored mail-core secret entry.")
    args = parser.parse_args()

    password = None
    if args.admin_initial_password_env:
        import os

        password = os.environ.get(args.admin_initial_password_env)
        if not password:
            raise SystemExit(f"{args.admin_initial_password_env} is not set")

    result = provision_controlled_domain(
        ControlledDomainProvisioningOptions(
            database_path=args.database,
            domain=args.domain,
            admin_email=args.admin_email,
            admin_display_name=args.admin_display_name,
            admin_initial_password=password,
            mailbox_local_part=args.mailbox_local_part,
            dkim_selector=args.dkim_selector,
            hostname=args.hostname,
            secrets_json=args.secrets_json,
            force_secret=args.force_secret,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
