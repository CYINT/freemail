from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanOptions:
    user_secrets: dict[str, str]
    skip_users_without_secret: bool = False


class MissingProvisioningSecretError(ValueError):
    pass


def build_apply_plan_status(connection: sqlite3.Connection, available_user_secrets: set[str]) -> dict[str, object]:
    connection.row_factory = sqlite3.Row
    active_domains = _domain_values(connection)
    active_dkim = _dkim_values(connection)
    accounts = _account_rows(connection)
    missing_secrets = sorted(
        str(row["email"]) for row in accounts if str(row["email"]).lower() not in available_user_secrets
    )
    account_alias_count = sum(len(_account_aliases(connection, str(row["email"]))) for row in accounts)
    operation_types = []
    if active_domains:
        operation_types.append("Domain")
    if active_dkim:
        operation_types.append("DkimSignature")
    if accounts and not missing_secrets:
        operation_types.append("Account")
    return {
        "ready": not missing_secrets,
        "operationTypes": operation_types,
        "domains": len(active_domains),
        "dkimKeys": len(active_dkim),
        "accounts": len(accounts),
        "aliases": account_alias_count,
        "missingProvisioningSecrets": missing_secrets,
    }


def build_apply_plan(connection: sqlite3.Connection, options: PlanOptions) -> list[dict[str, object]]:
    connection.row_factory = sqlite3.Row
    operations: list[dict[str, object]] = []
    _append_upsert(operations, "Domain", ["name"], _domain_values(connection))
    _append_upsert(operations, "DkimSignature", ["selector"], _dkim_values(connection))
    _append_upsert(operations, "Account", ["emailAddress"], _account_values(connection, options))
    return operations


def _append_upsert(
    operations: list[dict[str, object]],
    object_name: str,
    match_on: list[str],
    value: dict[str, dict[str, object]],
) -> None:
    if value:
        operations.append({"@type": "upsert", "object": object_name, "matchOn": match_on, "value": value})


def _domain_values(connection: sqlite3.Connection) -> dict[str, dict[str, object]]:
    return {
        _domain_ref(row["name"]): {
            "name": row["name"],
            "description": f"FreeMail hosted domain {row['name']}",
            "isEnabled": True,
        }
        for row in connection.execute("SELECT name FROM domains WHERE status = 'active' ORDER BY id")
    }


def _dkim_values(connection: sqlite3.Connection) -> dict[str, dict[str, object]]:
    values: dict[str, dict[str, object]] = {}
    rows = connection.execute(
        """
        SELECT domains.name AS domain_name, dkim_keys.selector, dkim_keys.private_key_pem
        FROM dkim_keys
        JOIN domains ON domains.id = dkim_keys.domain_id
        WHERE dkim_keys.status = 'active'
          AND domains.status = 'active'
        ORDER BY dkim_keys.id
        """
    )
    for row in rows:
        key = _client_ref("dkim", row["selector"], row["domain_name"])
        values[key] = {
            "@type": "Dkim1RsaSha256",
            "domainId": f"#{_domain_ref(row['domain_name'])}",
            "selector": row["selector"],
            "canonicalization": "relaxed/relaxed",
            "privateKey": {"@type": "Text", "secret": row["private_key_pem"]},
            "stage": "active",
        }
    return values


def _account_values(connection: sqlite3.Connection, options: PlanOptions) -> dict[str, dict[str, object]]:
    values: dict[str, dict[str, object]] = {}
    for row in _account_rows(connection):
        email = row["email"]
        secret = options.user_secrets.get(email)
        if not secret:
            if options.skip_users_without_secret:
                continue
            raise MissingProvisioningSecretError(f"Missing mail-core provisioning secret for {email}")
        local_part, domain = _split_email(email)
        values[_client_ref("account", email)] = {
            "@type": "User",
            "name": local_part,
            "emailAddress": email,
            "domainId": f"#{_domain_ref(domain)}",
            "description": row["display_name"],
            "aliases": _account_aliases(connection, email),
            "credentials": {
                "0": {
                    "@type": "Password",
                    "secret": secret,
                },
            },
            "encryptionAtRest": {"@type": "Disabled"},
            "memberGroupIds": {},
            "permissions": {"@type": "Inherit"},
            "quotas": {},
            "roles": {"@type": "User"},
        }
    return values


def _account_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT DISTINCT users.email, users.display_name
            FROM users
            JOIN mailboxes ON mailboxes.user_id = users.id
            JOIN domains ON domains.id = mailboxes.domain_id
            WHERE users.status = 'invited'
              AND mailboxes.status = 'active'
              AND domains.status = 'active'
            ORDER BY users.id
            """
        )
    )


def _account_aliases(connection: sqlite3.Connection, email: str) -> dict[str, dict[str, object]]:
    rows = connection.execute(
        """
        SELECT mailboxes.address
        FROM mailboxes
        JOIN users ON users.id = mailboxes.user_id
        JOIN domains ON domains.id = mailboxes.domain_id
        WHERE users.email = ? AND mailboxes.status = 'active' AND domains.status = 'active'
        UNION
        SELECT aliases.source AS address
        FROM aliases
        JOIN domains ON domains.name = substr(aliases.source, instr(aliases.source, '@') + 1)
        WHERE aliases.destination = ? AND aliases.status = 'active' AND domains.status = 'active'
        ORDER BY address
        """,
        [email, email],
    )
    aliases: dict[str, dict[str, object]] = {}
    for row in rows:
        if row["address"] == email:
            continue
        local_part, domain = _split_email(row["address"])
        aliases[str(len(aliases))] = {
            "name": local_part,
            "domainId": f"#{_domain_ref(domain)}",
        }
    return aliases


def _split_email(address: str) -> tuple[str, str]:
    local_part, separator, domain = address.partition("@")
    if not local_part or separator != "@" or not domain:
        raise ValueError(f"Invalid email address: {address}")
    return local_part, domain


def _domain_ref(domain: str) -> str:
    return _client_ref("domain", domain)


def _client_ref(*parts: str) -> str:
    raw = "-".join(parts).lower()
    return "".join(character if character.isalnum() else "-" for character in raw).strip("-")
