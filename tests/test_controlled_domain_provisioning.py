import json

from freemail_api.controlled_domain_provisioning import (
    ControlledDomainProvisioningOptions,
    provision_controlled_domain,
)
from freemail_api import database
from freemail_api.stalwart_plan import PlanOptions, build_apply_plan


def test_provision_controlled_domain_creates_release_ready_metadata_without_output_secrets(tmp_path):
    secrets_json = tmp_path / "secrets" / "mail-core-users.json"

    result = provision_controlled_domain(
        ControlledDomainProvisioningOptions(
            database_path=tmp_path / "freemail.sqlite",
            domain="Example.COM.",
            admin_email="Admin@Example.com",
            admin_display_name="Admin User",
            admin_initial_password="correct horse battery",
            secrets_json=secrets_json,
            hostname="freemail.kuzuryu.ai",
        )
    )

    assert result["domain"] == "example.com"
    assert result["adminEmail"] == "admin@example.com"
    assert result["created"] == {"domain": True, "user": True, "mailbox": True, "dkimKey": True}
    assert result["secrets"] == {
        "path": str(secrets_json),
        "mailCoreSecretWritten": True,
        "adminInitialPasswordGenerated": False,
        "credentialFreeOutput": True,
    }
    assert "correct horse battery" not in json.dumps(result)
    assert result["mailCorePlanStatus"]["ready"] is True
    assert result["mailCorePlanStatus"]["operationTypes"] == ["Domain", "DkimSignature", "Account"]
    assert {record["type"] for record in result["dnsGuidance"]["records"]} == {"MX", "TXT"}

    secrets_payload = json.loads(secrets_json.read_text(encoding="utf-8"))
    assert secrets_payload == {"admin@example.com": "correct horse battery"}
    with database.connect(str(tmp_path / "freemail.sqlite")) as connection:
        plan = build_apply_plan(connection, PlanOptions(user_secrets=secrets_payload))
    assert [operation["object"] for operation in plan] == ["Domain", "DkimSignature", "Account"]


def test_provision_controlled_domain_is_idempotent_and_does_not_overwrite_existing_secret(tmp_path):
    secrets_json = tmp_path / "secrets" / "mail-core-users.json"
    options = ControlledDomainProvisioningOptions(
        database_path=tmp_path / "freemail.sqlite",
        domain="example.com",
        admin_email="admin@example.com",
        admin_display_name="Admin User",
        admin_initial_password="first secret phrase",
        secrets_json=secrets_json,
    )
    first = provision_controlled_domain(options)
    second = provision_controlled_domain(
        ControlledDomainProvisioningOptions(
            database_path=tmp_path / "freemail.sqlite",
            domain="example.com",
            admin_email="admin@example.com",
            admin_display_name="Admin User",
            admin_initial_password="second secret phrase",
            secrets_json=secrets_json,
        )
    )

    assert first["created"] == {"domain": True, "user": True, "mailbox": True, "dkimKey": True}
    assert second["created"] == {"domain": False, "user": False, "mailbox": False, "dkimKey": False}
    assert second["secrets"]["mailCoreSecretWritten"] is False
    assert json.loads(secrets_json.read_text(encoding="utf-8")) == {"admin@example.com": "first secret phrase"}


def test_provision_controlled_domain_force_secret_updates_ignored_secret_mapping(tmp_path):
    secrets_json = tmp_path / "secrets" / "mail-core-users.json"
    provision_controlled_domain(
        ControlledDomainProvisioningOptions(
            database_path=tmp_path / "freemail.sqlite",
            domain="example.com",
            admin_email="admin@example.com",
            admin_display_name="Admin User",
            admin_initial_password="first secret phrase",
            secrets_json=secrets_json,
        )
    )
    result = provision_controlled_domain(
        ControlledDomainProvisioningOptions(
            database_path=tmp_path / "freemail.sqlite",
            domain="example.com",
            admin_email="admin@example.com",
            admin_display_name="Admin User",
            admin_initial_password="second secret phrase",
            secrets_json=secrets_json,
            force_secret=True,
        )
    )

    assert result["secrets"]["mailCoreSecretWritten"] is True
    assert json.loads(secrets_json.read_text(encoding="utf-8")) == {"admin@example.com": "second secret phrase"}


def test_provision_controlled_domain_rejects_mismatched_admin_domain(tmp_path):
    try:
        provision_controlled_domain(
            ControlledDomainProvisioningOptions(
                database_path=tmp_path / "freemail.sqlite",
                domain="example.com",
                admin_email="admin@other.example",
                admin_display_name="Admin User",
            )
        )
    except ValueError as error:
        assert str(error) == "admin email domain must match controlled domain"
    else:
        raise AssertionError("expected mismatched admin domain to fail")
