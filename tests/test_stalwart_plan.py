import sqlite3

import pytest

from freemail_api.database import (
    create_alias,
    create_dkim_key,
    create_domain,
    create_mailbox,
    create_user,
    initialize,
)
from freemail_api.schemas import AliasCreate, DkimKeyCreate, DomainCreate, MailboxCreate, UserCreate
from freemail_api.stalwart_plan import MissingProvisioningSecretError, PlanOptions, build_apply_plan


def test_build_apply_plan_exports_domains_dkim_accounts_and_aliases(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    initialize(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        domain = create_domain(connection, DomainCreate(name="example.com"), "test")
        user = create_user(
            connection,
            UserCreate(
                email="admin@example.com",
                displayName="Admin User",
                passwordHash="argon2id-placeholder-hash",
                isAdmin=True,
            ),
            "test",
        )
        create_mailbox(
            connection,
            MailboxCreate(userId=int(user["id"]), localPart="admin", domainId=int(domain["id"])),
            "test",
        )
        create_alias(
            connection,
            AliasCreate(source="hello@example.com", destination="admin@example.com"),
            "test",
        )
        create_dkim_key(
            connection,
            DkimKeyCreate(domainId=int(domain["id"]), selector="mail"),
            "v=DKIM1; k=rsa; p=public",
            "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "test",
        )

        plan = build_apply_plan(connection, PlanOptions(user_secrets={"admin@example.com": "mail-secret"}))

    assert [operation["object"] for operation in plan] == ["Domain", "DkimSignature", "Account", "EmailList"]
    assert plan[0]["id"] == "example.com"
    assert plan[1]["params"]["selector"] == "mail"
    assert plan[2]["params"]["emails"] == ["admin@example.com"]
    assert plan[2]["params"]["secrets"] == ["mail-secret"]
    assert plan[2]["params"]["roles"] == ["admin"]
    assert plan[3]["params"]["members"] == ["admin@example.com"]


def test_build_apply_plan_requires_user_secret_by_default(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    initialize(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        create_user(
            connection,
            UserCreate(email="admin@example.com", displayName="Admin User", passwordHash="argon2id-placeholder-hash"),
            "test",
        )

        with pytest.raises(MissingProvisioningSecretError):
            build_apply_plan(connection, PlanOptions(user_secrets={}))
