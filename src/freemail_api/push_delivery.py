from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


DEVELOPMENT_PROVIDERS = {"contract-only", "development"}


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
) -> PushDeliveryResult:
    normalized_provider = provider.strip().lower()
    if normalized_provider in DEVELOPMENT_PROVIDERS:
        digest = sha256(f"{normalized_provider}:{device_id}:{title}:{body}".encode("utf-8")).hexdigest()[:24]
        return PushDeliveryResult(delivered=True, provider_message_id=f"{normalized_provider}:{digest}")
    return PushDeliveryResult(
        delivered=False,
        error=f"push provider adapter is not configured for {provider}",
    )
