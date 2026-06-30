from pathlib import Path

from fastapi.testclient import TestClient

from freemail_api.main import create_app
from freemail_api.settings import Settings


ADMIN_TOKEN = "test-admin-token"
BOOTSTRAP_TOKEN = "test-bootstrap-token"


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=str(tmp_path / "freemail.sqlite"),
        admin_api_token=ADMIN_TOKEN,
        bootstrap_token=BOOTSTRAP_TOKEN,
        release_commit="test",
    )
    return TestClient(create_app(settings))


def admin_headers() -> dict[str, str]:
    return {"X-FreeMail-Admin-Token": ADMIN_TOKEN}


def bootstrap_headers() -> dict[str, str]:
    return {"X-FreeMail-Bootstrap-Token": BOOTSTRAP_TOKEN}


def test_admin_api_requires_configured_token(tmp_path):
    settings = Settings(database_path=str(tmp_path / "freemail.sqlite"), release_commit="test")

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/admin/domains")

    assert response.status_code == 503
    assert response.json()["detail"] == "Admin API token is not configured"


def test_bootstrap_requires_configured_token(tmp_path):
    settings = Settings(database_path=str(tmp_path / "freemail.sqlite"), release_commit="test")

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/bootstrap/admin",
            json={
                "domainName": "example.com",
                "email": "admin@example.com",
                "displayName": "Admin User",
                "passwordHash": "argon2id-placeholder-hash",
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
                "passwordHash": "argon2id-placeholder-hash",
                "isAdmin": True,
            },
        )
        assert user.status_code == 201
        assert user.json()["email"] == "admin@example.com"
        assert user.json()["isAdmin"] is True
        assert "passwordHash" not in user.json()

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


def test_bootstrap_creates_only_first_admin_domain_and_mailbox(tmp_path):
    with make_client(tmp_path) as client:
        payload = {
            "domainName": "Example.COM",
            "email": "Admin@Example.com",
            "displayName": "Admin User",
            "passwordHash": "argon2id-placeholder-hash",
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
