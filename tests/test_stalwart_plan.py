import sqlite3

import pytest

from freemail_api.database import (
    create_alias,
    create_dkim_key,
    create_domain,
    create_mailbox,
    create_user,
    initialize,
    update_status,
)
from freemail_api.schemas import AliasCreate, DkimKeyCreate, DomainCreate, MailboxCreate, StoredUserCreate
from freemail_api.stalwart_plan import MissingProvisioningSecretError, PlanOptions, build_apply_plan, build_apply_plan_status


def test_build_apply_plan_exports_domains_dkim_accounts_and_aliases(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    initialize(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        domain = create_domain(connection, DomainCreate(name="example.com"), "test")
        user = create_user(
            connection,
            StoredUserCreate(
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

    assert [operation["@type"] for operation in plan] == ["upsert", "upsert", "upsert"]
    assert [operation["object"] for operation in plan] == ["Domain", "DkimSignature", "Account"]
    assert plan[0]["matchOn"] == ["name"]
    assert plan[0]["value"]["domain-example-com"]["name"] == "example.com"
    assert plan[1]["matchOn"] == ["selector"]
    assert plan[1]["value"]["dkim-mail-example-com"]["@type"] == "Dkim1RsaSha256"
    assert plan[1]["value"]["dkim-mail-example-com"]["selector"] == "mail"
    assert plan[1]["value"]["dkim-mail-example-com"]["privateKey"] == {
        "@type": "Text",
        "secret": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
    }
    assert plan[2]["matchOn"] == ["name", "domainId"]
    assert plan[2]["value"]["account-admin-example-com"]["name"] == "admin"
    assert plan[2]["value"]["account-admin-example-com"]["domainId"] == "#domain-example-com"
    assert "emailAddress" not in plan[2]["value"]["account-admin-example-com"]
    assert plan[2]["value"]["account-admin-example-com"]["credentials"]["0"] == {
        "@type": "Password",
        "secret": "mail-secret",
    }
    assert plan[2]["value"]["account-admin-example-com"]["aliases"] == {
        "0": {"name": "hello", "domainId": "#domain-example-com"}
    }
    assert plan[2]["value"]["account-admin-example-com"]["roles"] == {"@type": "User"}


def test_build_apply_plan_status_reports_counts_and_missing_secrets(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    initialize(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        domain = create_domain(connection, DomainCreate(name="example.com"), "test")
        user = create_user(
            connection,
            StoredUserCreate(
                email="admin@example.com",
                displayName="Admin User",
                passwordHash="argon2id-placeholder-hash",
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

        missing = build_apply_plan_status(connection, set())
        ready = build_apply_plan_status(connection, {"admin@example.com"})

    assert missing == {
        "ready": False,
        "operationTypes": ["Domain", "DkimSignature"],
        "domains": 1,
        "dkimKeys": 1,
        "accounts": 1,
        "aliases": 1,
        "missingProvisioningSecrets": ["admin@example.com"],
    }
    assert ready["ready"] is True
    assert ready["operationTypes"] == ["Domain", "DkimSignature", "Account"]
    assert ready["missingProvisioningSecrets"] == []


def test_build_apply_plan_requires_user_secret_by_default(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    initialize(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        domain = create_domain(connection, DomainCreate(name="example.com"), "test")
        user = create_user(
            connection,
            StoredUserCreate(email="admin@example.com", displayName="Admin User", passwordHash="argon2id-placeholder-hash"),
            "test",
        )
        create_mailbox(
            connection,
            MailboxCreate(userId=int(user["id"]), localPart="admin", domainId=int(domain["id"])),
            "test",
        )

        with pytest.raises(MissingProvisioningSecretError):
            build_apply_plan(connection, PlanOptions(user_secrets={}))


def test_build_apply_plan_excludes_suspended_domain_and_mailbox(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    initialize(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        active_domain = create_domain(connection, DomainCreate(name="active.example"), "test")
        suspended_domain = create_domain(connection, DomainCreate(name="suspended.example"), "test")
        active_user = create_user(
            connection,
            StoredUserCreate(email="active@active.example", displayName="Active User", passwordHash="argon2id-placeholder"),
            "test",
        )
        suspended_domain_user = create_user(
            connection,
            StoredUserCreate(
                email="user@suspended.example",
                displayName="Suspended Domain User",
                passwordHash="argon2id-placeholder",
            ),
            "test",
        )
        suspended_mailbox_user = create_user(
            connection,
            StoredUserCreate(
                email="disabled@active.example",
                displayName="Disabled Mailbox User",
                passwordHash="argon2id-placeholder",
            ),
            "test",
        )
        create_mailbox(
            connection,
            MailboxCreate(userId=int(active_user["id"]), localPart="active", domainId=int(active_domain["id"])),
            "test",
        )
        create_mailbox(
            connection,
            MailboxCreate(
                userId=int(suspended_domain_user["id"]),
                localPart="user",
                domainId=int(suspended_domain["id"]),
            ),
            "test",
        )
        disabled_mailbox = create_mailbox(
            connection,
            MailboxCreate(
                userId=int(suspended_mailbox_user["id"]),
                localPart="disabled",
                domainId=int(active_domain["id"]),
            ),
            "test",
        )
        update_status(connection, "domains", int(suspended_domain["id"]), "suspended", "test")
        update_status(connection, "mailboxes", int(disabled_mailbox["id"]), "suspended", "test")

        plan = build_apply_plan(
            connection,
            PlanOptions(
                user_secrets={
                    "active@active.example": "active-secret",
                    "user@suspended.example": "domain-secret",
                    "disabled@active.example": "mailbox-secret",
                }
            ),
        )

    assert [operation["object"] for operation in plan] == ["Domain", "Account"]
    assert set(plan[0]["value"]) == {"domain-active-example"}
    assert set(plan[1]["value"]) == {"account-active-active-example"}


def test_build_apply_plan_excludes_suspended_alias_and_dkim_key(tmp_path):
    db_path = tmp_path / "freemail.sqlite"
    initialize(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        domain = create_domain(connection, DomainCreate(name="example.com"), "test")
        user = create_user(
            connection,
            StoredUserCreate(email="admin@example.com", displayName="Admin User", passwordHash="argon2id-placeholder"),
            "test",
        )
        create_mailbox(
            connection,
            MailboxCreate(userId=int(user["id"]), localPart="admin", domainId=int(domain["id"])),
            "test",
        )
        alias = create_alias(
            connection,
            AliasCreate(source="hello@example.com", destination="admin@example.com"),
            "test",
        )
        dkim_key = create_dkim_key(
            connection,
            DkimKeyCreate(domainId=int(domain["id"]), selector="mail"),
            "v=DKIM1; k=rsa; p=public",
            "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "test",
        )
        update_status(connection, "aliases", int(alias["id"]), "suspended", "test")
        update_status(connection, "dkim_keys", int(dkim_key["id"]), "suspended", "test")

        plan = build_apply_plan(connection, PlanOptions(user_secrets={"admin@example.com": "mail-secret"}))

    assert [operation["object"] for operation in plan] == ["Domain", "Account"]
    assert plan[1]["value"]["account-admin-example-com"]["aliases"] == {}
