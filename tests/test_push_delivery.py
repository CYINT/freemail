import json

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import NoEncryption
from cryptography.hazmat.primitives.serialization import PrivateFormat

from freemail_api.push_delivery import dispatch_apns
from freemail_api.push_delivery import dispatch_fcm
from freemail_api.push_delivery import dispatch_push_notification
from freemail_api.push_delivery import PushDeliveryConfig


class FakeResponse:
    def __init__(self, payload=None, headers=None):
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_dispatch_push_notification_requires_encrypted_token_for_fcm():
    result = dispatch_push_notification(provider="fcm", device_id="device-1", title="Title", body="Body")

    assert result.delivered is False
    assert result.error == "encrypted push token is not available for fcm"


def test_dispatch_fcm_uses_http_v1_message_api(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url == "https://oauth2.googleapis.com/token":
            return FakeResponse({"access_token": "access-token"})
        return FakeResponse({"name": "projects/freemail/messages/123"})

    monkeypatch.setattr("freemail_api.push_delivery.httpx.post", fake_post)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    service_account = {
        "client_email": "fcm@example.iam.gserviceaccount.com",
        "private_key": private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode("ascii"),
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    result = dispatch_fcm(
        push_token="device-token",
        title="FreeMail",
        body="New message",
        config=PushDeliveryConfig(
            fcm_project_id="freemail-project",
            fcm_service_account_json=json.dumps(service_account),
        ),
    )

    assert result.delivered is True
    assert result.provider_message_id == "projects/freemail/messages/123"
    assert calls[1][0] == "https://fcm.googleapis.com/v1/projects/freemail-project/messages:send"
    assert calls[1][1]["headers"] == {"Authorization": "Bearer access-token"}
    assert calls[1][1]["json"]["message"]["token"] == "device-token"
    assert calls[1][1]["json"]["message"]["notification"] == {"title": "FreeMail", "body": "New message"}


def test_dispatch_apns_uses_token_auth_provider_api(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(headers={"apns-id": "apns-message-id"})

    monkeypatch.setattr("freemail_api.push_delivery.httpx.Client", FakeClient)
    private_key = ec.generate_private_key(ec.SECP256R1())

    result = dispatch_apns(
        push_token="apns-token",
        title="FreeMail",
        body="New message",
        config=PushDeliveryConfig(
            apns_team_id="TEAMID1234",
            apns_key_id="KEYID1234",
            apns_private_key_pem=private_key.private_bytes(
                Encoding.PEM,
                PrivateFormat.PKCS8,
                NoEncryption(),
            ).decode("ascii"),
            apns_bundle_id="technology.cyint.freemail",
            apns_use_sandbox=True,
        ),
    )

    assert result.delivered is True
    assert result.provider_message_id == "apns-message-id"
    assert calls[0] == ("client", {"http2": True, "timeout": 10.0})
    assert calls[1][0] == "https://api.sandbox.push.apple.com/3/device/apns-token"
    assert calls[1][1]["headers"]["apns-topic"] == "technology.cyint.freemail"
    assert calls[1][1]["headers"]["apns-push-type"] == "alert"
    assert calls[1][1]["headers"]["authorization"].startswith("bearer ")
