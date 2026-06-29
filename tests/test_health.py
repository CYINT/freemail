from fastapi.testclient import TestClient

from freemail_api.main import app


client = TestClient(app)


def test_health_reports_vpn_only_release_metadata():
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "freemail"
    assert payload["hostname"] == "freemail.kuzuryu.ai"
    assert payload["vpnOnly"] is True
    assert payload["release"]["commit"]


def test_product_scope_includes_server_web_and_mobile():
    response = client.get("/api/v1/product")

    assert response.status_code == 200
    payload = response.json()
    assert payload["license"] == "AGPL-3.0-or-later"
    assert "mail-core" in payload["scope"]
    assert "webmail" in payload["scope"]
    assert "mobile-client" in payload["scope"]


def test_deployment_is_not_public_internet():
    response = client.get("/api/v1/deployment")

    assert response.status_code == 200
    payload = response.json()
    assert payload["hostname"] == "freemail.kuzuryu.ai"
    assert payload["exposure"] == "vpn-only"
    assert payload["publicInternet"] is False
