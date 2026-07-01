from fastapi.testclient import TestClient

from freemail_api.main import app, create_app
from freemail_api.settings import Settings


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
    assert payload["components"] == {
        "adminApi": "ready",
        "mailCore": "runtime-ready",
        "webmail": "beta-ready",
        "mobile": "source-ready",
    }


def test_api_responses_include_security_headers():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert "camera=()" in response.headers["permissions-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_product_scope_includes_server_web_and_mobile():
    response = client.get("/api/v1/product")

    assert response.status_code == 200
    payload = response.json()
    assert payload["license"] == "AGPL-3.0-or-later"
    assert "mail-core" in payload["scope"]
    assert "webmail" in payload["scope"]
    assert "mobile-client" in payload["scope"]


def test_product_readiness_reports_component_evidence_and_release_blockers():
    response = client.get("/api/v1/product/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"] == "FreeMail"
    assert payload["license"] == "AGPL-3.0-or-later"
    assert payload["credentialFreePublicRepo"] is True
    assert payload["vpnOnly"] is True
    assert payload["releaseReady"] is False
    assert payload["components"]["adminApi"]["status"] == "ready"
    assert payload["components"]["mailCore"]["status"] == "runtime-ready"
    assert payload["components"]["webmail"]["status"] == "beta-ready"
    assert payload["components"]["mobile"]["status"] == "source-ready"
    assert "decision-owner private-beta acceptance" in payload["releaseBlockers"]
    assert "real signed native mobile builds" in payload["releaseBlockers"]


def test_deployment_is_not_public_internet():
    response = client.get("/api/v1/deployment")

    assert response.status_code == 200
    payload = response.json()
    assert payload["hostname"] == "freemail.kuzuryu.ai"
    assert payload["exposure"] == "vpn-only"
    assert payload["publicInternet"] is False


def test_metadata_readiness_reports_sqlite_schema_without_paths(tmp_path):
    database_path = tmp_path / "freemail.sqlite"
    isolated_app = create_app(Settings(database_path=str(database_path)))
    with TestClient(isolated_app) as isolated_client:
        response = isolated_client.get("/api/v1/metadata/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["backend"] == "sqlite"
    assert payload["schemaRevision"] == "sqlite-schema-v1"
    assert all(check["status"] == "pass" for check in payload["checks"])
    assert "path" not in payload
