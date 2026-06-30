from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import database
from .dkim import generate_dkim_key_pair
from .dns_policy import domain_dns_records
from .passwords import hash_initial_password
from .schemas import DkimKeyCreate, DomainCreate, MailboxCreate, StoredUserCreate
from .stalwart_plan import build_apply_plan_status


@dataclass(frozen=True)
class ControlledDomainProvisioningOptions:
    database_path: Path
    domain: str
    admin_email: str
    admin_display_name: str
    admin_initial_password: str | None = None
    mailbox_local_part: str | None = None
    dkim_selector: str = "mail"
    hostname: str = "freemail.kuzuryu.ai"
    secrets_json: Path = Path("secrets/mail-core-users.json")
    actor: str = "controlled-domain-provisioning"
    force_secret: bool = False


def provision_controlled_domain(options: ControlledDomainProvisioningOptions) -> dict[str, Any]:
    domain = _normalize_domain(options.domain)
    email = _normalize_email(options.admin_email)
    local_part = options.mailbox_local_part or email.partition("@")[0]
    if email.partition("@")[2] != domain:
        raise ValueError("admin email domain must match controlled domain")

    database.initialize(str(options.database_path))
    generated_secret = options.admin_initial_password is None
    account_secret = options.admin_initial_password or _generate_account_secret()

    with database.connect(str(options.database_path)) as connection:
        domain_row, domain_created = _get_or_create_domain(connection, domain, options.actor)
        user_row, user_created = _get_or_create_user(
            connection,
            email=email,
            display_name=options.admin_display_name,
            account_secret=account_secret,
            actor=options.actor,
        )
        mailbox_row, mailbox_created = _get_or_create_mailbox(
            connection,
            user_id=int(user_row["id"]),
            local_part=local_part,
            domain_id=int(domain_row["id"]),
            actor=options.actor,
        )
        dkim_row, dkim_created = _get_or_create_dkim_key(
            connection,
            domain_id=int(domain_row["id"]),
            selector=options.dkim_selector,
            actor=options.actor,
        )
        secrets_written = _write_mail_core_secret(
            options.secrets_json,
            email=email,
            secret=account_secret,
            should_write=user_created or options.force_secret,
        )
        plan_status = build_apply_plan_status(connection, {email} if secrets_written or _secret_exists(options.secrets_json, email) else set())
        dns_records = domain_dns_records(
            domain=domain,
            hostname=options.hostname,
            dkim_keys=[dkim_row],
        )

    return {
        "domain": domain,
        "adminEmail": email,
        "mailbox": str(mailbox_row["address"]),
        "dkimSelector": str(dkim_row["selector"]),
        "hostname": options.hostname,
        "created": {
            "domain": domain_created,
            "user": user_created,
            "mailbox": mailbox_created,
            "dkimKey": dkim_created,
        },
        "secrets": {
            "path": str(options.secrets_json),
            "mailCoreSecretWritten": secrets_written,
            "adminInitialPasswordGenerated": generated_secret,
            "credentialFreeOutput": True,
        },
        "dnsGuidance": {
            "records": [record.model_dump(by_alias=True) for record in dns_records],
        },
        "mailCorePlanStatus": plan_status,
        "nextSteps": [
            "Publish the DNS guidance records for the controlled domain.",
            "Run collect_stalwart_apply_evidence.py with the ignored mail-core secrets file.",
            "Run collect_controlled_domain_evidence.py after DNS propagation and controlled mail-flow checks.",
            "Refresh backup/restore evidence after controlled-domain provisioning changes runtime state.",
        ],
    }


def _get_or_create_domain(connection: sqlite3.Connection, domain: str, actor: str) -> tuple[sqlite3.Row, bool]:
    row = connection.execute("SELECT * FROM domains WHERE name = ?", [domain]).fetchone()
    if row is not None:
        return row, False
    return database.create_domain(connection, DomainCreate(name=domain), actor), True


def _get_or_create_user(
    connection: sqlite3.Connection,
    *,
    email: str,
    display_name: str,
    account_secret: str,
    actor: str,
) -> tuple[sqlite3.Row, bool]:
    row = connection.execute("SELECT * FROM users WHERE email = ?", [email]).fetchone()
    if row is not None:
        return row, False
    user = database.create_user(
        connection,
        StoredUserCreate(
            email=email,
            display_name=display_name,
            password_hash=hash_initial_password(account_secret),
            is_admin=True,
            admin_role="owner",
        ),
        actor,
    )
    return user, True


def _get_or_create_mailbox(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    local_part: str,
    domain_id: int,
    actor: str,
) -> tuple[sqlite3.Row, bool]:
    domain = database.get_domain(connection, domain_id)
    address = f"{local_part.lower()}@{domain['name']}"
    row = connection.execute("SELECT * FROM mailboxes WHERE address = ?", [address]).fetchone()
    if row is not None:
        return row, False
    mailbox = database.create_mailbox(
        connection,
        MailboxCreate(user_id=user_id, local_part=local_part, domain_id=domain_id),
        actor,
    )
    return mailbox, True


def _get_or_create_dkim_key(
    connection: sqlite3.Connection,
    *,
    domain_id: int,
    selector: str,
    actor: str,
) -> tuple[sqlite3.Row, bool]:
    normalized_selector = selector.lower()
    row = connection.execute(
        "SELECT * FROM dkim_keys WHERE domain_id = ? AND selector = ?",
        [domain_id, normalized_selector],
    ).fetchone()
    if row is not None:
        return row, False
    public_txt, private_key_pem = generate_dkim_key_pair()
    dkim_key = database.create_dkim_key(
        connection,
        DkimKeyCreate(domainId=domain_id, selector=normalized_selector),
        public_txt,
        private_key_pem,
        actor,
    )
    return dkim_key, True


def _write_mail_core_secret(path: Path, *, email: str, secret: str, should_write: bool) -> bool:
    if not should_write:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_secret_payload(path)
    if email in payload and not should_write:
        return False
    payload[email] = secret
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def _secret_exists(path: Path, email: str) -> bool:
    return email in _load_secret_payload(path)


def _load_secret_payload(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
        raise ValueError("mail-core secrets JSON must be an object mapping email addresses to passwords")
    return {key.lower(): value for key, value in payload.items()}


def _generate_account_secret() -> str:
    return secrets.token_urlsafe(32)


def _normalize_domain(value: str) -> str:
    normalized = value.strip().lower().rstrip(".")
    if "." not in normalized or normalized.startswith(".") or normalized.endswith("."):
        raise ValueError("domain must be a fully qualified DNS name")
    return normalized


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("admin email must be an email address")
    return normalized
