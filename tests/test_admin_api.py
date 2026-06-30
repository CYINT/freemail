from hashlib import sha256
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from freemail_api.main import create_app
from freemail_api.push_delivery import PushDeliveryResult
from freemail_api.settings import Settings


ADMIN_TOKEN = "test-admin-token"
BOOTSTRAP_TOKEN = "test-bootstrap-token"


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=str(tmp_path / "freemail.sqlite"),
        admin_api_token=ADMIN_TOKEN,
        bootstrap_token=BOOTSTRAP_TOKEN,
        session_secret="test-session-secret",
        push_token_secret="test-push-token-secret",
        release_commit="test",
    )
    return TestClient(create_app(settings))


def admin_headers() -> dict[str, str]:
    return {"X-FreeMail-Admin-Token": ADMIN_TOKEN}


def bootstrap_headers() -> dict[str, str]:
    return {"X-FreeMail-Bootstrap-Token": BOOTSTRAP_TOKEN}


def test_admin_api_requires_configured_token(tmp_path):
    settings = Settings(database_path=str(tmp_path / "freemail.sqlite"), release_commit="test", session_secret=None)

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/admin/domains")

    assert response.status_code == 503
    assert response.json()["detail"] == "Admin API token is not configured and no valid admin session was provided"


def test_bootstrap_requires_configured_token(tmp_path):
    settings = Settings(database_path=str(tmp_path / "freemail.sqlite"), release_commit="test", session_secret=None)

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/bootstrap/admin",
            json={
                "domainName": "example.com",
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
                "mailboxLocalPart": "admin",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Bootstrap token is not configured"


def test_admin_api_rejects_invalid_token(tmp_path):
    with TestClient(
        create_app(
            Settings(
                database_path=str(tmp_path / "freemail.sqlite"),
                admin_api_token=ADMIN_TOKEN,
                release_commit="test",
            )
        )
    ) as client:
        response = client.get("/api/v1/admin/domains", headers={"X-FreeMail-Admin-Token": "wrong"})

    assert response.status_code == 401


def test_admin_can_create_domain_user_mailbox_alias_and_audit_log(tmp_path):
    with make_client(tmp_path) as client:
        domain = client.post(
            "/api/v1/admin/domains",
            headers=admin_headers(),
            json={"name": "Example.COM"},
        )
        assert domain.status_code == 201
        assert domain.json()["name"] == "example.com"

        user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "Admin@Example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
            },
        )
        assert user.status_code == 201
        assert user.json()["email"] == "admin@example.com"
        assert user.json()["isAdmin"] is True
        assert "passwordHash" not in user.json()
        with sqlite3.connect(tmp_path / "freemail.sqlite") as connection:
            stored_hash = connection.execute("SELECT password_hash FROM users WHERE email = ?", ["admin@example.com"]).fetchone()[0]
        assert stored_hash.startswith("$argon2id$")
        assert stored_hash != "correct horse battery"

        mailbox = client.post(
            "/api/v1/admin/mailboxes",
            headers=admin_headers(),
            json={
                "userId": user.json()["id"],
                "localPart": "Admin",
                "domainId": domain.json()["id"],
            },
        )
        assert mailbox.status_code == 201
        assert mailbox.json()["address"] == "admin@example.com"

        alias = client.post(
            "/api/v1/admin/aliases",
            headers=admin_headers(),
            json={
                "source": "hello@example.com",
                "destination": "admin@example.com",
            },
        )
        assert alias.status_code == 201
        assert alias.json()["source"] == "hello@example.com"

        audit_log = client.get("/api/v1/admin/audit-log", headers=admin_headers())
        assert audit_log.status_code == 200
        assert [entry["action"] for entry in audit_log.json()] == [
            "domain.create",
            "user.invite",
            "mailbox.create",
            "alias.create",
        ]


def test_admin_user_create_rejects_client_supplied_password_hash(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "admin@example.com",
                "displayName": "Admin User",
                "passwordHash": "argon2id-placeholder-hash",
            },
        )

    assert response.status_code == 422
    assert any(error["loc"][-1] == "initialPassword" for error in response.json()["detail"])


def test_admin_password_login_allows_bearer_admin_api_without_static_token(tmp_path):
    settings = Settings(
        database_path=str(tmp_path / "freemail.sqlite"),
        bootstrap_token=BOOTSTRAP_TOKEN,
        release_commit="test",
    )
    with TestClient(create_app(settings)) as client:
        bootstrap = client.post(
            "/api/v1/bootstrap/admin",
            headers=bootstrap_headers(),
            json={
                "domainName": "example.com",
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
                "mailboxLocalPart": "admin",
            },
        )
        login = client.post(
            "/api/v1/admin/session",
            json={"email": "admin@example.com", "password": "correct horse battery"},
        )
        domains = client.get("/api/v1/admin/domains", headers={"Authorization": f"Bearer {login.json()['token']}"})

    assert bootstrap.status_code == 201
    assert login.status_code == 200
    assert login.json()["email"] == "admin@example.com"
    assert "token" in login.json()
    assert domains.status_code == 200
    assert domains.json()[0]["name"] == "example.com"


def test_admin_password_login_rejects_bad_password(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
            },
        )
        response = client.post(
            "/api/v1/admin/session",
            json={"email": "admin@example.com", "password": "wrong password"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Admin authentication failed"


def test_admin_session_revoke_blocks_bearer_admin_api(tmp_path):
    settings = Settings(
        database_path=str(tmp_path / "freemail.sqlite"),
        bootstrap_token=BOOTSTRAP_TOKEN,
        release_commit="test",
    )
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/v1/bootstrap/admin",
            headers=bootstrap_headers(),
            json={
                "domainName": "example.com",
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
                "mailboxLocalPart": "admin",
            },
        )
        login = client.post(
            "/api/v1/admin/session",
            json={"email": "admin@example.com", "password": "correct horse battery"},
        )
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        logout = client.delete("/api/v1/admin/session", headers=headers)
        response = client.get("/api/v1/admin/domains", headers=headers)

    assert logout.status_code == 200
    assert logout.json()["revoked"] is True
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid admin session"


def test_suspended_admin_blocks_existing_bearer_admin_session(tmp_path):
    with make_client(tmp_path) as client:
        user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
            },
        ).json()
        login = client.post(
            "/api/v1/admin/session",
            json={"email": "admin@example.com", "password": "correct horse battery"},
        )
        client.patch(
            f"/api/v1/admin/users/{user['id']}/status",
            headers=admin_headers(),
            json={"status": "suspended"},
        )
        response = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {login.json()['token']}"})

    assert login.status_code == 200
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid admin session"


def test_owner_can_create_scoped_admin_and_role_is_returned(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "operator@example.com",
                "displayName": "Operator User",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
                "adminRole": "operator",
            },
        )

    assert response.status_code == 201
    assert response.json()["isAdmin"] is True
    assert response.json()["adminRole"] == "operator"


def test_admin_role_can_invite_member_but_cannot_grant_admin(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "manager@example.com",
                "displayName": "Manager User",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
                "adminRole": "admin",
            },
        )
        login = client.post(
            "/api/v1/admin/session",
            json={"email": "manager@example.com", "password": "correct horse battery"},
        )
        bearer_headers = {"Authorization": f"Bearer {login.json()['token']}"}
        invited = client.post(
            "/api/v1/admin/users",
            headers=bearer_headers,
            json={
                "email": "member@example.com",
                "displayName": "Member User",
                "initialPassword": "correct horse battery",
            },
        )
        denied = client.post(
            "/api/v1/admin/users",
            headers=bearer_headers,
            json={
                "email": "other-admin@example.com",
                "displayName": "Other Admin",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
                "adminRole": "operator",
            },
        )

    assert login.status_code == 200
    assert invited.status_code == 201
    assert invited.json()["isAdmin"] is False
    assert invited.json()["adminRole"] == "member"
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Admin role lacks admin.grant permission"


def test_operator_can_manage_domains_but_cannot_invite_users(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "operator@example.com",
                "displayName": "Operator User",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
                "adminRole": "operator",
            },
        )
        login = client.post(
            "/api/v1/admin/session",
            json={"email": "operator@example.com", "password": "correct horse battery"},
        )
        bearer_headers = {"Authorization": f"Bearer {login.json()['token']}"}
        domain = client.post("/api/v1/admin/domains", headers=bearer_headers, json={"name": "example.com"})
        denied = client.post(
            "/api/v1/admin/users",
            headers=bearer_headers,
            json={
                "email": "member@example.com",
                "displayName": "Member User",
                "initialPassword": "correct horse battery",
            },
        )

    assert login.status_code == 200
    assert domain.status_code == 201
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Admin role lacks admin.users permission"


def test_auditor_can_read_but_cannot_mutate_admin_metadata(tmp_path):
    with make_client(tmp_path) as client:
        client.post("/api/v1/admin/domains", headers=admin_headers(), json={"name": "example.com"})
        client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "auditor@example.com",
                "displayName": "Auditor User",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
                "adminRole": "auditor",
            },
        )
        login = client.post(
            "/api/v1/admin/session",
            json={"email": "auditor@example.com", "password": "correct horse battery"},
        )
        bearer_headers = {"Authorization": f"Bearer {login.json()['token']}"}
        domains = client.get("/api/v1/admin/domains", headers=bearer_headers)
        denied = client.post("/api/v1/admin/domains", headers=bearer_headers, json={"name": "other.example"})

    assert login.status_code == 200
    assert domains.status_code == 200
    assert domains.json()[0]["name"] == "example.com"
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Admin role lacks admin.manage permission"


def test_operator_can_read_mail_core_sync_plan_status_without_secret_material(tmp_path):
    with make_client(tmp_path) as client:
        domain = client.post("/api/v1/admin/domains", headers=admin_headers(), json={"name": "example.com"}).json()
        user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
            },
        ).json()
        client.post(
            "/api/v1/admin/mailboxes",
            headers=admin_headers(),
            json={"userId": user["id"], "localPart": "admin", "domainId": domain["id"]},
        )
        client.post(
            "/api/v1/admin/aliases",
            headers=admin_headers(),
            json={"source": "hello@example.com", "destination": "admin@example.com"},
        )
        client.post(
            "/api/v1/admin/dkim-keys",
            headers=admin_headers(),
            json={"domainId": domain["id"], "selector": "mail"},
        )
        client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "operator@example.com",
                "displayName": "Operator User",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
                "adminRole": "operator",
            },
        )
        login = client.post(
            "/api/v1/admin/session",
            json={"email": "operator@example.com", "password": "correct horse battery"},
        )
        response = client.post(
            "/api/v1/admin/mail-core/sync-plan/status",
            headers={"Authorization": f"Bearer {login.json()['token']}"},
            json={"availableUserSecrets": ["admin@example.com"]},
        )

    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "operationTypes": ["Domain", "DkimSignature", "Account"],
        "domains": 1,
        "dkimKeys": 1,
        "accounts": 1,
        "aliases": 1,
        "missingProvisioningSecrets": [],
    }
    assert "PRIVATE KEY" not in response.text
    assert "correct horse battery" not in response.text


def test_mail_core_sync_plan_status_reports_missing_account_secrets(tmp_path):
    with make_client(tmp_path) as client:
        domain = client.post("/api/v1/admin/domains", headers=admin_headers(), json={"name": "example.com"}).json()
        user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
            },
        ).json()
        client.post(
            "/api/v1/admin/mailboxes",
            headers=admin_headers(),
            json={"userId": user["id"], "localPart": "admin", "domainId": domain["id"]},
        )
        response = client.post(
            "/api/v1/admin/mail-core/sync-plan/status",
            headers=admin_headers(),
            json={"availableUserSecrets": []},
        )

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["missingProvisioningSecrets"] == ["admin@example.com"]
    assert response.json()["operationTypes"] == ["Domain"]


def test_auditor_cannot_read_mail_core_sync_plan_status(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "auditor@example.com",
                "displayName": "Auditor User",
                "initialPassword": "correct horse battery",
                "isAdmin": True,
                "adminRole": "auditor",
            },
        )
        login = client.post(
            "/api/v1/admin/session",
            json={"email": "auditor@example.com", "password": "correct horse battery"},
        )
        response = client.post(
            "/api/v1/admin/mail-core/sync-plan/status",
            headers={"Authorization": f"Bearer {login.json()['token']}"},
            json={"availableUserSecrets": []},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role lacks admin.manage permission"


def test_non_admin_user_role_is_forced_to_member(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "member@example.com",
                "displayName": "Member User",
                "initialPassword": "correct horse battery",
                "adminRole": "owner",
            },
        )

    assert response.status_code == 201
    assert response.json()["isAdmin"] is False
    assert response.json()["adminRole"] == "member"


def test_admin_can_suspend_and_reactivate_domain_user_and_mailbox(tmp_path):
    with make_client(tmp_path) as client:
        domain = client.post("/api/v1/admin/domains", headers=admin_headers(), json={"name": "example.com"}).json()
        user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
            },
        ).json()
        mailbox = client.post(
            "/api/v1/admin/mailboxes",
            headers=admin_headers(),
            json={"userId": user["id"], "localPart": "admin", "domainId": domain["id"]},
        ).json()

        suspended_domain = client.patch(
            f"/api/v1/admin/domains/{domain['id']}/status",
            headers=admin_headers(),
            json={"status": "suspended"},
        )
        suspended_user = client.patch(
            f"/api/v1/admin/users/{user['id']}/status",
            headers=admin_headers(),
            json={"status": "suspended"},
        )
        suspended_mailbox = client.patch(
            f"/api/v1/admin/mailboxes/{mailbox['id']}/status",
            headers=admin_headers(),
            json={"status": "suspended"},
        )
        reactivated_user = client.patch(
            f"/api/v1/admin/users/{user['id']}/status",
            headers=admin_headers(),
            json={"status": "invited"},
        )
        audit_log = client.get("/api/v1/admin/audit-log", headers=admin_headers())

    assert suspended_domain.status_code == 200
    assert suspended_domain.json()["status"] == "suspended"
    assert suspended_user.status_code == 200
    assert suspended_user.json()["status"] == "suspended"
    assert suspended_mailbox.status_code == 200
    assert suspended_mailbox.json()["status"] == "suspended"
    assert reactivated_user.status_code == 200
    assert reactivated_user.json()["status"] == "invited"
    assert [entry["action"] for entry in audit_log.json()][-4:] == [
        "domain.suspend",
        "user.suspend",
        "mailbox.suspend",
        "user.activate",
    ]


def test_admin_can_suspend_alias_and_dkim_key(tmp_path):
    with make_client(tmp_path) as client:
        domain = client.post("/api/v1/admin/domains", headers=admin_headers(), json={"name": "example.com"}).json()
        user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
            },
        ).json()
        client.post(
            "/api/v1/admin/mailboxes",
            headers=admin_headers(),
            json={"userId": user["id"], "localPart": "admin", "domainId": domain["id"]},
        )
        alias = client.post(
            "/api/v1/admin/aliases",
            headers=admin_headers(),
            json={"source": "hello@example.com", "destination": "admin@example.com"},
        ).json()
        dkim_key = client.post(
            "/api/v1/admin/dkim-keys",
            headers=admin_headers(),
            json={"domainId": domain["id"], "selector": "mail"},
        ).json()

        suspended_alias = client.patch(
            f"/api/v1/admin/aliases/{alias['id']}/status",
            headers=admin_headers(),
            json={"status": "suspended"},
        )
        suspended_dkim = client.patch(
            f"/api/v1/admin/dkim-keys/{dkim_key['id']}/status",
            headers=admin_headers(),
            json={"status": "suspended"},
        )
        dns_guidance = client.get(f"/api/v1/admin/domains/{domain['id']}/dns", headers=admin_headers())
        audit_log = client.get("/api/v1/admin/audit-log", headers=admin_headers())

    assert suspended_alias.status_code == 200
    assert suspended_alias.json()["status"] == "suspended"
    assert suspended_dkim.status_code == 200
    assert suspended_dkim.json()["status"] == "suspended"
    assert not any(record["name"] == "mail._domainkey.example.com" for record in dns_guidance.json()["records"])
    assert [entry["action"] for entry in audit_log.json()][-2:] == ["alias.suspend", "dkim_key.suspend"]


def test_admin_status_update_rejects_invalid_resource_status(tmp_path):
    with make_client(tmp_path) as client:
        domain = client.post("/api/v1/admin/domains", headers=admin_headers(), json={"name": "example.com"}).json()
        response = client.patch(
            f"/api/v1/admin/domains/{domain['id']}/status",
            headers=admin_headers(),
            json={"status": "invited"},
        )

    assert response.status_code == 422
    assert "domains status must be one of" in response.json()["detail"]


def test_suspended_mailbox_blocks_mailbox_api_access(tmp_path, monkeypatch):
    def fake_snapshot(**_kwargs):
        raise AssertionError("IMAP snapshot should not run for suspended mailbox")

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", fake_snapshot)
    with make_client(tmp_path) as client:
        domain = client.post("/api/v1/admin/domains", headers=admin_headers(), json={"name": "example.com"}).json()
        user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
            },
        ).json()
        mailbox = client.post(
            "/api/v1/admin/mailboxes",
            headers=admin_headers(),
            json={"userId": user["id"], "localPart": "admin", "domainId": domain["id"]},
        ).json()
        client.patch(
            f"/api/v1/admin/mailboxes/{mailbox['id']}/status",
            headers=admin_headers(),
            json={"status": "suspended"},
        )
        response = client.get(
            "/api/v1/mailbox/snapshot",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
        )
        session_response = client.post(
            "/api/v1/mailbox/session",
            json={"email": "admin@example.com", "password": "secret"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Mailbox is suspended"
    assert session_response.status_code == 403
    assert session_response.json()["detail"] == "Mailbox is suspended"


def test_suspended_user_blocks_existing_bearer_session(tmp_path, monkeypatch):
    class Snapshot:
        def as_dict(self):
            return {"email": "admin@example.com", "folders": [], "messages": []}

    calls = []

    def fake_snapshot(**_kwargs):
        calls.append("snapshot")
        return Snapshot()

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", fake_snapshot)
    with make_client(tmp_path) as client:
        domain = client.post("/api/v1/admin/domains", headers=admin_headers(), json={"name": "example.com"}).json()
        user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers(),
            json={
                "email": "admin@example.com",
                "displayName": "Admin User",
                "initialPassword": "correct horse battery",
            },
        ).json()
        client.post(
            "/api/v1/admin/mailboxes",
            headers=admin_headers(),
            json={"userId": user["id"], "localPart": "admin", "domainId": domain["id"]},
        )
        session_response = client.post(
            "/api/v1/mailbox/session",
            json={"email": "admin@example.com", "password": "secret"},
        )
        token = session_response.json()["token"]
        client.patch(
            f"/api/v1/admin/users/{user['id']}/status",
            headers=admin_headers(),
            json={"status": "suspended"},
        )
        response = client.get("/api/v1/mailbox/snapshot", headers={"Authorization": f"Bearer {token}"})

    assert session_response.status_code == 200
    assert response.status_code == 403
    assert response.json()["detail"] == "Mailbox is suspended"
    assert calls == ["snapshot"]


def test_bootstrap_creates_only_first_admin_domain_and_mailbox(tmp_path):
    with make_client(tmp_path) as client:
        payload = {
            "domainName": "Example.COM",
            "email": "Admin@Example.com",
            "displayName": "Admin User",
            "initialPassword": "correct horse battery",
            "mailboxLocalPart": "Admin",
        }

        response = client.post("/api/v1/bootstrap/admin", headers=bootstrap_headers(), json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["domain"]["name"] == "example.com"
        assert body["user"]["email"] == "admin@example.com"
        assert body["user"]["isAdmin"] is True
        assert "passwordHash" not in body["user"]
        assert body["mailbox"]["address"] == "admin@example.com"

        second_response = client.post("/api/v1/bootstrap/admin", headers=bootstrap_headers(), json=payload)
        assert second_response.status_code == 409


def test_admin_api_returns_conflict_for_duplicate_domain(tmp_path):
    with make_client(tmp_path) as client:
        payload = {"name": "example.com"}

        assert client.post("/api/v1/admin/domains", headers=admin_headers(), json=payload).status_code == 201
        response = client.post("/api/v1/admin/domains", headers=admin_headers(), json=payload)

    assert response.status_code == 409


def test_mailbox_creation_requires_existing_domain_and_user(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/admin/mailboxes",
            headers=admin_headers(),
            json={"userId": 1, "localPart": "admin", "domainId": 1},
        )

    assert response.status_code == 404


def test_admin_can_generate_dkim_key_and_dns_guidance(tmp_path):
    with make_client(tmp_path) as client:
        domain = client.post(
            "/api/v1/admin/domains",
            headers=admin_headers(),
            json={"name": "example.com"},
        )
        assert domain.status_code == 201

        dkim_key = client.post(
            "/api/v1/admin/dkim-keys",
            headers=admin_headers(),
            json={"domainId": domain.json()["id"], "selector": "mail"},
        )
        assert dkim_key.status_code == 201
        dkim_body = dkim_key.json()
        assert dkim_body["dnsName"] == "mail._domainkey.example.com"
        assert dkim_body["publicTxt"].startswith("v=DKIM1; k=rsa; p=")
        assert dkim_body["privateKeyPem"].startswith("-----BEGIN PRIVATE KEY-----")

        listed_keys = client.get("/api/v1/admin/dkim-keys", headers=admin_headers())
        assert listed_keys.status_code == 200
        assert listed_keys.json()[0]["dnsName"] == "mail._domainkey.example.com"
        assert "privateKeyPem" not in listed_keys.json()[0]

        dns_guidance = client.get(
            f"/api/v1/admin/domains/{domain.json()['id']}/dns",
            headers=admin_headers(),
        )
        assert dns_guidance.status_code == 200
        records = dns_guidance.json()["records"]
        assert {record["type"] for record in records} == {"MX", "TXT"}
        assert any(record["name"] == "example.com" and record["value"] == "v=spf1 mx -all" for record in records)
        assert any(record["name"] == "_dmarc.example.com" for record in records)
        assert any(record["name"] == "mail._domainkey.example.com" for record in records)


def test_admin_can_verify_dns_guidance_posture(tmp_path):
    with make_client(tmp_path) as client:
        domain = client.post(
            "/api/v1/admin/domains",
            headers=admin_headers(),
            json={"name": "example.com"},
        )
        dkim_key = client.post(
            "/api/v1/admin/dkim-keys",
            headers=admin_headers(),
            json={"domainId": domain.json()["id"], "selector": "mail"},
        )
        guidance = client.get(f"/api/v1/admin/domains/{domain.json()['id']}/dns", headers=admin_headers()).json()
        observed = [
            {"type": record["type"], "name": record["name"], "values": [record["value"]]}
            for record in guidance["records"]
        ]
        response = client.post(
            f"/api/v1/admin/domains/{domain.json()['id']}/dns/verify",
            headers=admin_headers(),
            json={"observedRecords": observed},
        )

    assert dkim_key.status_code == 201
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert all(check["found"] for check in response.json()["checks"])


def test_admin_dns_verify_reports_missing_records(tmp_path):
    with make_client(tmp_path) as client:
        domain = client.post(
            "/api/v1/admin/domains",
            headers=admin_headers(),
            json={"name": "example.com"},
        )
        response = client.post(
            f"/api/v1/admin/domains/{domain.json()['id']}/dns/verify",
            headers=admin_headers(),
            json={
                "observedRecords": [
                    {"type": "MX", "name": "example.com", "values": ["10 freemail.kuzuryu.ai."]}
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert [check["found"] for check in response.json()["checks"]] == [True, False, False]


def test_mailbox_snapshot_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/mailbox/snapshot")

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_snapshot_allows_loopback_web_preview_cors(tmp_path):
    with make_client(tmp_path) as client:
        response = client.options(
            "/api/v1/mailbox/snapshot",
            headers={
                "Origin": "http://127.0.0.1:18091",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-FreeMail-Mailbox-Email, X-FreeMail-Mailbox-Password",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:18091"


def test_mailbox_send_allows_loopback_web_preview_cors(tmp_path):
    with make_client(tmp_path) as client:
        response = client.options(
            "/api/v1/mailbox/send",
            headers={
                "Origin": "http://127.0.0.1:18091",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "Content-Type, X-FreeMail-Mailbox-Email, X-FreeMail-Mailbox-Password"
                ),
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:18091"


def test_mailbox_archive_allows_loopback_web_preview_cors(tmp_path):
    with make_client(tmp_path) as client:
        response = client.options(
            "/api/v1/mailbox/message/archive",
            headers={
                "Origin": "http://127.0.0.1:18091",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "Content-Type, X-FreeMail-Mailbox-Email, X-FreeMail-Mailbox-Password"
                ),
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:18091"


def test_mailbox_snapshot_returns_imap_adapter_payload(tmp_path, monkeypatch):
    class Snapshot:
        def as_dict(self):
            return {
                "email": "admin@example.com",
                "folders": [{"name": "INBOX", "messageCount": 1, "unreadCount": 0}],
                "messages": [
                    {
                        "folder": "INBOX",
                        "messageId": "1",
                        "subject": "Hello",
                        "sender": "sender@example.net",
                        "recipients": "admin@example.com",
                        "date": "",
                        "unread": False,
                    }
                ],
            }

    def fake_snapshot(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "INBOX"
        assert kwargs["limit"] == 1
        return Snapshot()

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", fake_snapshot)

    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/mailbox/snapshot?limit=1",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
        )

    assert response.status_code == 200
    assert response.json()["folders"][0]["name"] == "INBOX"
    assert response.json()["messages"][0]["subject"] == "Hello"


def test_mailbox_session_create_and_bearer_snapshot(tmp_path, monkeypatch):
    class Snapshot:
        def as_dict(self):
            return {
                "email": "admin@example.com",
                "folders": [{"name": "INBOX", "messageCount": 1, "unreadCount": 0}],
                "messages": [],
            }

    calls = []

    def fake_snapshot(**kwargs):
        calls.append(kwargs)
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        return Snapshot()

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", fake_snapshot)

    with make_client(tmp_path) as client:
        session_response = client.post(
            "/api/v1/mailbox/session",
            json={"email": "admin@example.com", "password": "secret"},
        )
        assert session_response.status_code == 200
        token = session_response.json()["token"]

        snapshot_response = client.get(
            "/api/v1/mailbox/snapshot",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["email"] == "admin@example.com"
    assert len(calls) == 2


def test_mailbox_session_requires_configured_secret(tmp_path, monkeypatch):
    class Snapshot:
        def as_dict(self):
            return {"email": "admin@example.com", "folders": [], "messages": []}

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", lambda **_kwargs: Snapshot())
    settings = Settings(database_path=str(tmp_path / "freemail.sqlite"), release_commit="test", session_secret=None)

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/mailbox/session",
            json={"email": "admin@example.com", "password": "secret"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Mailbox sessions are not configured"


def test_mailbox_session_delete_revokes_token(tmp_path, monkeypatch):
    class Snapshot:
        def as_dict(self):
            return {"email": "admin@example.com", "folders": [], "messages": []}

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", lambda **_kwargs: Snapshot())

    with make_client(tmp_path) as client:
        session_response = client.post(
            "/api/v1/mailbox/session",
            json={"email": "admin@example.com", "password": "secret"},
        )
        token = session_response.json()["token"]
        delete_response = client.delete("/api/v1/mailbox/session", headers={"Authorization": f"Bearer {token}"})
        snapshot_response = client.get("/api/v1/mailbox/snapshot", headers={"Authorization": f"Bearer {token}"})

    assert delete_response.status_code == 200
    assert delete_response.json()["revoked"] is True
    assert snapshot_response.status_code == 401


def test_mailbox_push_devices_require_bearer_session(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/push/devices",
            json={
                "deviceId": "device-123",
                "platform": "development",
                "pushToken": "provider-token-123",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_push_device_register_list_and_revoke(tmp_path, monkeypatch):
    class Snapshot:
        def as_dict(self):
            return {"email": "admin@example.com", "folders": [], "messages": []}

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", lambda **_kwargs: Snapshot())

    with make_client(tmp_path) as client:
        session_response = client.post(
            "/api/v1/mailbox/session",
            json={"email": "admin@example.com", "password": "secret"},
        )
        token = session_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        register_response = client.post(
            "/api/v1/mailbox/push/devices",
            headers=headers,
            json={
                "deviceId": "device-123",
                "platform": "development",
                "pushToken": "provider-token-123",
                "provider": "contract-only",
            },
        )
        list_response = client.get("/api/v1/mailbox/push/devices", headers=headers)
        revoke_response = client.delete("/api/v1/mailbox/push/devices/device-123", headers=headers)
        revoked_list_response = client.get("/api/v1/mailbox/push/devices", headers=headers)

    assert register_response.status_code == 200
    registered = register_response.json()
    assert registered["mailboxEmail"] == "admin@example.com"
    assert registered["deviceId"] == "device-123"
    assert registered["enabled"] is True
    assert "pushToken" not in registered
    assert "pushTokenHash" not in registered
    assert list_response.status_code == 200
    assert list_response.json()[0]["deviceId"] == "device-123"
    assert revoke_response.status_code == 200
    assert revoke_response.json() == {"revoked": True, "deviceId": "device-123"}
    assert revoked_list_response.json()[0]["enabled"] is False
    with sqlite3.connect(tmp_path / "freemail.sqlite") as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT push_token_hash, encrypted_push_token FROM mailbox_push_devices").fetchone()
    assert row["push_token_hash"] == sha256("provider-token-123".encode("utf-8")).hexdigest()
    assert row["push_token_hash"] != "provider-token-123"
    assert row["encrypted_push_token"] is not None
    assert row["encrypted_push_token"] != "provider-token-123"


def test_mailbox_push_notifications_require_bearer_session(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/push/notifications",
            json={"title": "FreeMail", "body": "New message"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_push_notifications_dispatch_development_provider(tmp_path, monkeypatch):
    class Snapshot:
        def as_dict(self):
            return {"email": "admin@example.com", "folders": [], "messages": []}

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", lambda **_kwargs: Snapshot())

    with make_client(tmp_path) as client:
        session_response = client.post(
            "/api/v1/mailbox/session",
            json={"email": "admin@example.com", "password": "secret"},
        )
        token = session_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post(
            "/api/v1/mailbox/push/devices",
            headers=headers,
            json={
                "deviceId": "device-123",
                "platform": "development",
                "pushToken": "provider-token-123",
                "provider": "development",
            },
        )
        create_response = client.post(
            "/api/v1/mailbox/push/notifications",
            headers=headers,
            json={"title": "FreeMail", "body": "New message"},
        )
        list_response = client.get("/api/v1/mailbox/push/notifications", headers=headers)

    assert create_response.status_code == 200
    created = create_response.json()
    assert len(created) == 1
    assert created[0]["mailboxEmail"] == "admin@example.com"
    assert created[0]["deviceId"] == "device-123"
    assert created[0]["provider"] == "development"
    assert created[0]["status"] == "delivered"
    assert created[0]["providerMessageId"].startswith("development:")
    assert created[0]["lastError"] is None
    assert list_response.status_code == 200
    assert list_response.json()[0]["status"] == "delivered"
    with sqlite3.connect(tmp_path / "freemail.sqlite") as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT COUNT(*) AS count FROM mailbox_push_notifications").fetchone()
    assert row["count"] == 1


def test_mailbox_push_notifications_mark_unconfigured_provider_pending(tmp_path, monkeypatch):
    class Snapshot:
        def as_dict(self):
            return {"email": "admin@example.com", "folders": [], "messages": []}

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", lambda **_kwargs: Snapshot())

    with make_client(tmp_path) as client:
        session_response = client.post(
            "/api/v1/mailbox/session",
            json={"email": "admin@example.com", "password": "secret"},
        )
        token = session_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post(
            "/api/v1/mailbox/push/devices",
            headers=headers,
            json={
                "deviceId": "device-123",
                "platform": "android",
                "pushToken": "provider-token-123",
                "provider": "fcm",
            },
        )
        response = client.post(
            "/api/v1/mailbox/push/notifications",
            headers=headers,
            json={"title": "FreeMail", "body": "New message"},
        )

    assert response.status_code == 200
    notification = response.json()[0]
    assert notification["status"] == "pending_provider"
    assert notification["providerMessageId"] is None
    assert "fcm" in notification["lastError"].lower()


def test_mailbox_push_notifications_pass_decrypted_token_to_provider(tmp_path, monkeypatch):
    class Snapshot:
        def as_dict(self):
            return {"email": "admin@example.com", "folders": [], "messages": []}

    dispatch_calls = []

    def fake_dispatch(**kwargs):
        dispatch_calls.append(kwargs)
        return PushDeliveryResult(delivered=True, provider_message_id="provider-message-id")

    monkeypatch.setattr("freemail_api.main.list_mailbox_snapshot", lambda **_kwargs: Snapshot())
    monkeypatch.setattr("freemail_api.main.dispatch_push_notification", fake_dispatch)

    with make_client(tmp_path) as client:
        session_response = client.post(
            "/api/v1/mailbox/session",
            json={"email": "admin@example.com", "password": "secret"},
        )
        token = session_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post(
            "/api/v1/mailbox/push/devices",
            headers=headers,
            json={
                "deviceId": "device-123",
                "platform": "android",
                "pushToken": "provider-token-123",
                "provider": "fcm",
            },
        )
        response = client.post(
            "/api/v1/mailbox/push/notifications",
            headers=headers,
            json={"title": "FreeMail", "body": "New message"},
        )

    assert response.status_code == 200
    assert response.json()[0]["status"] == "delivered"
    assert dispatch_calls[0]["provider"] == "fcm"
    assert dispatch_calls[0]["push_token"] == "provider-token-123"


def test_mailbox_search_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/mailbox/search?folder=INBOX&query=hello")

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_search_requires_query(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/mailbox/search?folder=INBOX&query=%20",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "query is required"


def test_mailbox_search_returns_imap_results(tmp_path, monkeypatch):
    class Result:
        def as_dict(self):
            return {
                "email": "admin@example.com",
                "folder": "INBOX",
                "query": "hello",
                "messages": [
                    {
                        "folder": "INBOX",
                        "message_id": "1",
                        "subject": "Hello",
                        "sender": "sender@example.net",
                        "recipients": "admin@example.com",
                        "date": "",
                        "unread": False,
                    }
                ],
            }

    def fake_search(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "INBOX"
        assert kwargs["query"] == "hello"
        assert kwargs["limit"] == 10
        return Result()

    monkeypatch.setattr("freemail_api.main.search_mailbox_messages", fake_search)

    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/mailbox/search?folder=INBOX&query=hello&limit=10",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
        )

    assert response.status_code == 200
    assert response.json()["query"] == "hello"
    assert response.json()["messages"][0]["subject"] == "Hello"


def test_mailbox_contacts_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/mailbox/contacts")

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_contacts_validates_limit(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/mailbox/contacts?limit=501",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "limit must be between 1 and 500"


def test_mailbox_contacts_returns_imap_contacts(tmp_path, monkeypatch):
    class Result:
        def as_dict(self):
            return {
                "email": "admin@example.com",
                "folder": "INBOX",
                "contacts": [
                    {
                        "name": "Sender",
                        "email": "sender@example.net",
                        "message_count": 3,
                    }
                ],
            }

    def fake_contacts(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "INBOX"
        assert kwargs["limit"] == 10
        return Result()

    monkeypatch.setattr("freemail_api.main.list_mailbox_contacts", fake_contacts)

    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/mailbox/contacts?folder=INBOX&limit=10",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
        )

    assert response.status_code == 200
    assert response.json()["contacts"][0]["email"] == "sender@example.net"
    assert response.json()["contacts"][0]["messageCount"] == 3


def test_mailbox_folder_create_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post("/api/v1/mailbox/folder", json={"folder": "Clients"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_folder_create_returns_adapter_payload(tmp_path, monkeypatch):
    class Created:
        def as_dict(self):
            return {"folder": "Clients", "target_folder": None, "action": "create", "success": True}

    def fake_create(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "Clients"
        return Created()

    monkeypatch.setattr("freemail_api.main.create_mailbox_folder", fake_create)

    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/folder",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={"folder": "Clients"},
        )

    assert response.status_code == 200
    assert response.json() == {"folder": "Clients", "targetFolder": None, "action": "create", "success": True}


def test_mailbox_folder_rename_rejects_core_folders(tmp_path):
    with make_client(tmp_path) as client:
        response = client.patch(
            "/api/v1/mailbox/folder",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={"folder": "INBOX", "targetFolder": "Inbox old"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Core mailbox folders cannot be renamed"


def test_mailbox_folder_rename_returns_adapter_payload(tmp_path, monkeypatch):
    class Renamed:
        def as_dict(self):
            return {"folder": "Clients", "target_folder": "Customers", "action": "rename", "success": True}

    def fake_rename(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "Clients"
        assert kwargs["target_folder"] == "Customers"
        return Renamed()

    monkeypatch.setattr("freemail_api.main.rename_mailbox_folder", fake_rename)

    with make_client(tmp_path) as client:
        response = client.patch(
            "/api/v1/mailbox/folder",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={"folder": "Clients", "targetFolder": "Customers"},
        )

    assert response.status_code == 200
    assert response.json()["targetFolder"] == "Customers"


def test_mailbox_folder_delete_rejects_core_folders(tmp_path):
    with make_client(tmp_path) as client:
        response = client.request(
            "DELETE",
            "/api/v1/mailbox/folder",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={"folder": "INBOX"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Core mailbox folders cannot be deleted"


def test_mailbox_folder_delete_returns_adapter_payload(tmp_path, monkeypatch):
    class Deleted:
        def as_dict(self):
            return {"folder": "Customers", "target_folder": None, "action": "delete", "success": True}

    def fake_delete(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "Customers"
        return Deleted()

    monkeypatch.setattr("freemail_api.main.delete_mailbox_folder", fake_delete)

    with make_client(tmp_path) as client:
        response = client.request(
            "DELETE",
            "/api/v1/mailbox/folder",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={"folder": "Customers"},
        )

    assert response.status_code == 200
    assert response.json() == {"folder": "Customers", "targetFolder": None, "action": "delete", "success": True}


def test_mailbox_move_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/message/move",
            json={"folder": "INBOX", "messageId": "1", "targetFolder": "Deleted Items"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_move_returns_imap_move_payload(tmp_path, monkeypatch):
    class Moved:
        def as_dict(self):
            return {
                "folder": "INBOX",
                "message_id": "1",
                "target_folder": "Deleted Items",
                "moved": True,
            }

    def fake_move(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "INBOX"
        assert kwargs["message_id"] == "1"
        assert kwargs["target_folder"] == "Deleted Items"
        return Moved()

    monkeypatch.setattr("freemail_api.main.move_mailbox_message", fake_move)

    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/message/move",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={"folder": "INBOX", "messageId": "1", "targetFolder": "Deleted Items"},
        )

    assert response.status_code == 200
    assert response.json()["moved"] is True
    assert response.json()["targetFolder"] == "Deleted Items"


def test_mailbox_read_state_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/message/read-state",
            json={"folder": "INBOX", "messageId": "1", "read": True},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_read_state_returns_imap_state_payload(tmp_path, monkeypatch):
    class State:
        def as_dict(self):
            return {
                "folder": "INBOX",
                "message_id": "1",
                "read": True,
                "unread": False,
            }

    def fake_read_state(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "INBOX"
        assert kwargs["message_id"] == "1"
        assert kwargs["read"] is True
        return State()

    monkeypatch.setattr("freemail_api.main.set_mailbox_message_read_state", fake_read_state)

    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/message/read-state",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={"folder": "INBOX", "messageId": "1", "read": True},
        )

    assert response.status_code == 200
    assert response.json() == {"folder": "INBOX", "messageId": "1", "read": True, "unread": False}


def test_mailbox_message_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/mailbox/message?folder=INBOX&message_id=1")

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_message_returns_imap_detail_payload(tmp_path, monkeypatch):
    class Detail:
        def as_dict(self):
            return {
                "folder": "INBOX",
                "message_id": "1",
                "subject": "Hello",
                "sender": "sender@example.net",
                "recipients": "admin@example.com",
                "date": "",
                "unread": False,
                "body": "Body text",
                "attachments": [
                    {
                        "attachment_id": "0",
                        "filename": "report.txt",
                        "content_type": "text/plain",
                        "size": 6,
                    }
                ],
            }

    def fake_message(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "INBOX"
        assert kwargs["message_id"] == "1"
        return Detail()

    monkeypatch.setattr("freemail_api.main.get_mailbox_message", fake_message)

    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/mailbox/message?folder=INBOX&message_id=1",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
        )

    assert response.status_code == 200
    assert response.json()["subject"] == "Hello"
    assert response.json()["body"] == "Body text"
    assert response.json()["attachments"][0]["filename"] == "report.txt"


def test_mailbox_attachment_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/mailbox/message/attachment?folder=INBOX&message_id=1&attachment_id=0")

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_attachment_returns_download_payload(tmp_path, monkeypatch):
    class Attachment:
        filename = "report.txt"
        content_type = "text/plain"
        content = b"report"

    def fake_attachment(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "INBOX"
        assert kwargs["message_id"] == "1"
        assert kwargs["attachment_id"] == "0"
        return Attachment()

    monkeypatch.setattr("freemail_api.main.get_mailbox_attachment", fake_attachment)

    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/mailbox/message/attachment?folder=INBOX&message_id=1&attachment_id=0",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
        )

    assert response.status_code == 200
    assert response.content == b"report"
    assert response.headers["content-type"].startswith("text/plain")
    assert "report.txt" in response.headers["content-disposition"]


def test_mailbox_send_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/send",
            json={"recipients": ["admin@example.com"], "subject": "Hello", "body": "Test"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_archive_requires_mailbox_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/message/archive",
            json={"folder": "INBOX", "messageId": "1", "archiveFolder": "Archive"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Mailbox credentials required"


def test_mailbox_archive_returns_imap_adapter_payload(tmp_path, monkeypatch):
    class Archived:
        def as_dict(self):
            return {
                "folder": "INBOX",
                "message_id": "1",
                "archive_folder": "Archive",
                "archived": True,
            }

    def fake_archive(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["folder"] == "INBOX"
        assert kwargs["message_id"] == "1"
        assert kwargs["archive_folder"] == "Archive"
        return Archived()

    monkeypatch.setattr("freemail_api.main.archive_mailbox_message", fake_archive)

    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/message/archive",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={"folder": "INBOX", "messageId": "1", "archiveFolder": "Archive"},
        )

    assert response.status_code == 200
    assert response.json()["archived"] is True
    assert response.json()["archiveFolder"] == "Archive"


def test_mailbox_send_returns_submission_payload(tmp_path, monkeypatch):
    class Sent:
        def as_dict(self):
            return {
                "message_id": "<message@example.com>",
                "sender": "admin@example.com",
                "recipients": ["hello@example.com"],
                "subject": "Hello",
                "sent_folder": "Sent Items",
                "sent_folder_saved": True,
            }

    def fake_send(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["recipients"] == ["hello@example.com"]
        assert kwargs["subject"] == "Hello"
        assert kwargs["body"] == "Body"
        assert kwargs["imap_host"] == "127.0.0.1"
        assert kwargs["imap_port"] == 2993
        assert kwargs["attachments"][0].filename == "report.txt"
        return Sent()

    monkeypatch.setattr("freemail_api.main.send_mailbox_message", fake_send)

    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/send",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={
                "recipients": ["hello@example.com"],
                "subject": "Hello",
                "body": "Body",
                "attachments": [
                    {
                        "filename": "report.txt",
                        "contentType": "text/plain",
                        "contentBase64": "cmVwb3J0",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["messageId"] == "<message@example.com>"
    assert response.json()["sentFolder"] == "Sent Items"
    assert response.json()["sentFolderSaved"] is True


def test_mailbox_send_rejects_message_rate_limit_before_smtp(tmp_path, monkeypatch):
    calls = []

    class Sent:
        def as_dict(self):
            return {
                "message_id": "<message@example.com>",
                "sender": "admin@example.com",
                "recipients": ["hello@example.com"],
                "subject": "Hello",
                "sent_folder": "Sent Items",
                "sent_folder_saved": True,
            }

    def fake_send(**_kwargs):
        calls.append("send")
        return Sent()

    monkeypatch.setattr("freemail_api.main.send_mailbox_message", fake_send)
    settings = Settings(
        database_path=str(tmp_path / "freemail.sqlite"),
        admin_api_token=ADMIN_TOKEN,
        bootstrap_token=BOOTSTRAP_TOKEN,
        session_secret="test-session-secret",
        send_rate_window_seconds=3600,
        send_rate_max_messages=1,
        send_rate_max_recipients=10,
        release_commit="test",
    )

    with TestClient(create_app(settings)) as client:
        headers = {
            "X-FreeMail-Mailbox-Email": "admin@example.com",
            "X-FreeMail-Mailbox-Password": "secret",
        }
        first = client.post(
            "/api/v1/mailbox/send",
            headers=headers,
            json={"recipients": ["hello@example.com"], "subject": "Hello", "body": "Body"},
        )
        second = client.post(
            "/api/v1/mailbox/send",
            headers=headers,
            json={"recipients": ["hello@example.com"], "subject": "Hello again", "body": "Body"},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert "send rate limit" in second.json()["detail"]
    assert calls == ["send"]


def test_mailbox_send_rejects_recipient_rate_limit_before_smtp(tmp_path, monkeypatch):
    def fake_send(**_kwargs):
        raise AssertionError("SMTP send should not run for rejected rate-limit payload")

    monkeypatch.setattr("freemail_api.main.send_mailbox_message", fake_send)
    settings = Settings(
        database_path=str(tmp_path / "freemail.sqlite"),
        admin_api_token=ADMIN_TOKEN,
        bootstrap_token=BOOTSTRAP_TOKEN,
        session_secret="test-session-secret",
        send_rate_window_seconds=3600,
        send_rate_max_messages=10,
        send_rate_max_recipients=1,
        release_commit="test",
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/mailbox/send",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={
                "recipients": ["hello@example.com", "ops@example.com"],
                "subject": "Hello",
                "body": "Body",
            },
        )

    assert response.status_code == 429
    assert "recipient rate limit" in response.json()["detail"]


def test_mailbox_send_rejects_unsupported_attachment_content_type(tmp_path, monkeypatch):
    def fake_send(**_kwargs):
        raise AssertionError("SMTP send should not run for rejected attachments")

    monkeypatch.setattr("freemail_api.main.send_mailbox_message", fake_send)

    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/send",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={
                "recipients": ["hello@example.com"],
                "subject": "Hello",
                "body": "Body",
                "attachments": [
                    {
                        "filename": "data.bin",
                        "contentType": "application/octet-stream",
                        "contentBase64": "AA==",
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert "Unsupported attachment content type" in response.json()["detail"]


def test_mailbox_send_rejects_oversized_attachment(tmp_path, monkeypatch):
    def fake_send(**_kwargs):
        raise AssertionError("SMTP send should not run for rejected attachments")

    monkeypatch.setattr("freemail_api.main.send_mailbox_message", fake_send)
    settings = Settings(
        database_path=str(tmp_path / "freemail.sqlite"),
        admin_api_token=ADMIN_TOKEN,
        bootstrap_token=BOOTSTRAP_TOKEN,
        session_secret="test-session-secret",
        max_attachment_bytes=3,
        release_commit="test",
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/mailbox/send",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={
                "recipients": ["hello@example.com"],
                "subject": "Hello",
                "body": "Body",
                "attachments": [
                    {
                        "filename": "report.txt",
                        "contentType": "text/plain",
                        "contentBase64": "cmVwb3J0",
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert "exceeds 3 bytes" in response.json()["detail"]
