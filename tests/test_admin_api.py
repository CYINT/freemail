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
            }

    def fake_send(**kwargs):
        assert kwargs["email"] == "admin@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["recipients"] == ["hello@example.com"]
        assert kwargs["subject"] == "Hello"
        assert kwargs["body"] == "Body"
        return Sent()

    monkeypatch.setattr("freemail_api.main.send_mailbox_message", fake_send)

    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/mailbox/send",
            headers={
                "X-FreeMail-Mailbox-Email": "admin@example.com",
                "X-FreeMail-Mailbox-Password": "secret",
            },
            json={"recipients": ["hello@example.com"], "subject": "Hello", "body": "Body"},
        )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["messageId"] == "<message@example.com>"
