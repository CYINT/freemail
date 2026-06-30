from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import time

from . import database


class OutboundRateLimitExceeded(ValueError):
    pass


@dataclass(frozen=True)
class OutboundRatePolicy:
    window_seconds: int
    max_messages: int
    max_recipients: int

    @property
    def enabled(self) -> bool:
        return self.window_seconds > 0 and (self.max_messages > 0 or self.max_recipients > 0)


def enforce_outbound_rate_limit(
    connection: sqlite3.Connection,
    *,
    email: str,
    recipient_count: int,
    policy: OutboundRatePolicy,
    now: int | None = None,
) -> None:
    if not policy.enabled:
        return
    current_time = int(time.time()) if now is None else now
    since = current_time - policy.window_seconds
    database.delete_old_outbound_send_events(connection, before=since)
    message_count, recent_recipients = database.count_outbound_send_events(connection, email=email, since=since)
    if policy.max_messages > 0 and message_count + 1 > policy.max_messages:
        raise OutboundRateLimitExceeded("Outbound send rate limit exceeded for this mailbox")
    if policy.max_recipients > 0 and recent_recipients + recipient_count > policy.max_recipients:
        raise OutboundRateLimitExceeded("Outbound recipient rate limit exceeded for this mailbox")


def record_outbound_send(
    connection: sqlite3.Connection,
    *,
    email: str,
    recipient_count: int,
    now: int | None = None,
) -> None:
    current_time = int(time.time()) if now is None else now
    database.record_outbound_send_event(
        connection,
        email=email,
        recipient_count=recipient_count,
        created_at=current_time,
    )
