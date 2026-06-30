from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanOptions:
    user_secrets: dict[str, str]
    skip_users_without_secret: bool = False


class MissingProvisioningSecretError(ValueError):
    pass


def build_apply_plan(connection: sqlite3.Connection, options: PlanOptions) -> list[dict[str, object]]:
    connection.row_factory = sqlite3.Row
    operations: list[dict[str, object]] = []
    operations.extend(_domain_operations(connection))
    operations.extend(_dkim_operations(connection))
    operations.extend(_account_operations(connection, options))
    operations.extend(_alias_operations(connection))
    return operations


def _domain_operations(connection: sqlite3.Connection) -> list[dict[str, object]]:
    return [
        {
            "type": "upsert",
            "object": "Domain",
            "id": row["name"],
            "params": {"description": f"FreeMail hosted domain {row['name']}"},
        }
        for row in connection.execute("SELECT name FROM domains WHERE status = 'active' ORDER BY id")
    ]


def _dkim_operations(connection: sqlite3.Connection) -> list[dict[str, object]]:
    operations: list[dict[str, object]] = []
    rows = connection.execute(
        """
        SELECT domains.name AS domain_name, dkim_keys.selector, dkim_keys.private_key_pem
        FROM dkim_keys
        JOIN domains ON domains.id = dkim_keys.domain_id
        WHERE dkim_keys.status = 'active'
        ORDER BY dkim_keys.id
        """
    )
    for row in rows:
        operations.append(
            {
                "type": "upsert",
                "object": "DkimSignature",
                "id": f"{row['selector']}._domainkey.{row['domain_name']}",
                "params": {
                    "domain": row["domain_name"],
                    "selector": row["selector"],
                    "algorithm": "rsa-sha256",
                    "private-key": row["private_key_pem"],
                },
            }
        )
    return operations


def _account_operations(connection: sqlite3.Connection, options: PlanOptions) -> list[dict[str, object]]:
    operations: list[dict[str, object]] = []
    rows = connection.execute(
        """
        SELECT users.email, users.display_name, users.is_admin, mailboxes.address
        FROM users
        LEFT JOIN mailboxes ON mailboxes.user_id = users.id
        WHERE users.status = 'invited'
        ORDER BY users.id, mailboxes.id
        """
    )
    seen_accounts: set[str] = set()
    for row in rows:
        email = row["email"]
        if email in seen_accounts:
            continue
        seen_accounts.add(email)
        secret = options.user_secrets.get(email)
        if not secret:
            if options.skip_users_without_secret:
                continue
            raise MissingProvisioningSecretError(f"Missing mail-core provisioning secret for {email}")
        operations.append(
            {
                "type": "upsert",
                "object": "Account",
                "id": email,
                "params": {
                    "name": row["display_name"],
                    "type": "individual",
                    "emails": _mailbox_addresses(connection, email),
                    "secrets": [secret],
                    "roles": ["admin"] if int(row["is_admin"]) else [],
                },
            }
        )
    return operations


def _mailbox_addresses(connection: sqlite3.Connection, email: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT mailboxes.address
        FROM mailboxes
        JOIN users ON users.id = mailboxes.user_id
        WHERE users.email = ? AND mailboxes.status = 'active'
        ORDER BY mailboxes.id
        """,
        [email],
    )
    return [row["address"] for row in rows]


def _alias_operations(connection: sqlite3.Connection) -> list[dict[str, object]]:
    return [
        {
            "type": "upsert",
            "object": "EmailList",
            "id": row["source"],
            "params": {
                "description": f"FreeMail alias {row['source']}",
                "members": [row["destination"]],
            },
        }
        for row in connection.execute(
            "SELECT source, destination FROM aliases WHERE status = 'active' ORDER BY id"
        )
    ]
