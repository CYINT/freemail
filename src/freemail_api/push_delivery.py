from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
import json
import time
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import utils
from cryptography.hazmat.primitives.serialization import load_pem_private_key
import httpx


DEVELOPMENT_PROVIDERS = {"contract-only", "development"}
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_TOKEN_URL = "https://oauth2.googleapis.com/token"
FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
APNS_PRODUCTION_URL = "https://api.push.apple.com/3/device/{device_token}"
APNS_SANDBOX_URL = "https://api.sandbox.push.apple.com/3/device/{device_token}"


@dataclass(frozen=True)
class PushDeliveryConfig:
    fcm_project_id: str | None = None
    fcm_service_account_json: str | None = None
    apns_team_id: str | None = None
    apns_key_id: str | None = None
    apns_private_key_pem: str | None = None
    apns_bundle_id: str | None = None
    apns_use_sandbox: bool = False
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class PushDeliveryResult:
    delivered: bool
    provider_message_id: str | None = None
    error: str | None = None


def dispatch_push_notification(
    *,
    provider: str,
    device_id: str,
    title: str,
    body: str,
    push_token: str | None = None,
    config: PushDeliveryConfig | None = None,
) -> PushDeliveryResult:
    normalized_provider = provider.strip().lower()
    if normalized_provider in DEVELOPMENT_PROVIDERS:
        digest = sha256(f"{normalized_provider}:{device_id}:{title}:{body}".encode("utf-8")).hexdigest()[:24]
        return PushDeliveryResult(delivered=True, provider_message_id=f"{normalized_provider}:{digest}")
    if not push_token:
        return PushDeliveryResult(delivered=False, error=f"encrypted push token is not available for {provider}")
    active_config = config or PushDeliveryConfig()
    if normalized_provider == "fcm":
        return dispatch_fcm(push_token=push_token, title=title, body=body, config=active_config)
    if normalized_provider == "apns":
        return dispatch_apns(push_token=push_token, title=title, body=body, config=active_config)
    return PushDeliveryResult(
        delivered=False,
        error=f"push provider adapter is not configured for {provider}",
    )


def dispatch_fcm(*, push_token: str, title: str, body: str, config: PushDeliveryConfig) -> PushDeliveryResult:
    if not config.fcm_project_id or not config.fcm_service_account_json:
        return PushDeliveryResult(delivered=False, error="FCM credentials are not configured")
    try:
        service_account = json.loads(config.fcm_service_account_json)
        access_token = _fcm_access_token(service_account, timeout_seconds=config.timeout_seconds)
        response = httpx.post(
            FCM_SEND_URL.format(project_id=config.fcm_project_id),
            headers={"Authorization": f"Bearer {access_token}"},
            json={"message": {"token": push_token, "notification": {"title": title, "body": body}}},
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
    except (KeyError, TypeError, ValueError, httpx.HTTPError) as error:
        return PushDeliveryResult(delivered=False, error=f"FCM delivery failed: {error}")
    provider_message_id = str(response.json().get("name", "")).strip() or None
    return PushDeliveryResult(delivered=True, provider_message_id=provider_message_id)


def dispatch_apns(*, push_token: str, title: str, body: str, config: PushDeliveryConfig) -> PushDeliveryResult:
    required = [config.apns_team_id, config.apns_key_id, config.apns_private_key_pem, config.apns_bundle_id]
    if not all(required):
        return PushDeliveryResult(delivered=False, error="APNS credentials are not configured")
    url_template = APNS_SANDBOX_URL if config.apns_use_sandbox else APNS_PRODUCTION_URL
    try:
        with httpx.Client(http2=True, timeout=config.timeout_seconds) as client:
            response = client.post(
                url_template.format(device_token=push_token),
                headers={
                    "authorization": f"bearer {_apns_provider_token(config)}",
                    "apns-topic": str(config.apns_bundle_id),
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                },
                json={"aps": {"alert": {"title": title, "body": body}}},
            )
        response.raise_for_status()
    except (TypeError, ValueError, httpx.HTTPError) as error:
        return PushDeliveryResult(delivered=False, error=f"APNS delivery failed: {error}")
    provider_message_id = response.headers.get("apns-id")
    return PushDeliveryResult(delivered=True, provider_message_id=provider_message_id)


def _fcm_access_token(service_account: dict[str, Any], *, timeout_seconds: float) -> str:
    issued_at = int(time.time())
    assertion = _signed_jwt(
        header={"alg": "RS256", "typ": "JWT"},
        payload={
            "iss": service_account["client_email"],
            "scope": FCM_SCOPE,
            "aud": service_account.get("token_uri") or FCM_TOKEN_URL,
            "iat": issued_at,
            "exp": issued_at + 3600,
        },
        private_key_pem=service_account["private_key"],
        algorithm="RS256",
    )
    response = httpx.post(
        service_account.get("token_uri") or FCM_TOKEN_URL,
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    token = str(response.json()["access_token"]).strip()
    if not token:
        raise ValueError("FCM token endpoint returned an empty access token")
    return token


def _apns_provider_token(config: PushDeliveryConfig) -> str:
    return _signed_jwt(
        header={"alg": "ES256", "kid": config.apns_key_id},
        payload={"iss": config.apns_team_id, "iat": int(time.time())},
        private_key_pem=str(config.apns_private_key_pem),
        algorithm="ES256",
    )


def _signed_jwt(*, header: dict[str, object], payload: dict[str, object], private_key_pem: str, algorithm: str) -> str:
    signing_input = f"{_base64url_json(header)}.{_base64url_json(payload)}"
    private_key = load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    if algorithm == "RS256":
        signature = private_key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    elif algorithm == "ES256":
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise ValueError("APNS private key must be an EC private key")
        der_signature = private_key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        signature = _ecdsa_der_to_raw(der_signature, part_size=32)
    else:
        raise ValueError(f"unsupported JWT algorithm: {algorithm}")
    return f"{signing_input}.{_base64url(signature)}"


def _base64url_json(value: dict[str, object]) -> str:
    return _base64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _ecdsa_der_to_raw(signature: bytes, *, part_size: int) -> bytes:
    r, s = utils.decode_dss_signature(signature)
    return r.to_bytes(part_size, "big") + s.to_bytes(part_size, "big")
