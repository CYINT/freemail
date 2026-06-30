import pytest

from freemail_api import database
from freemail_api.outbound_policy import enforce_outbound_rate_limit
from freemail_api.outbound_policy import OutboundRateLimitExceeded
from freemail_api.outbound_policy import OutboundRatePolicy
from freemail_api.outbound_policy import record_outbound_send


def test_outbound_policy_allows_and_records_send(tmp_path):
    path = tmp_path / "freemail.sqlite"
    database.initialize(str(path))
    with database.connect(str(path)) as connection:
        policy = OutboundRatePolicy(window_seconds=60, max_messages=2, max_recipients=3)

        enforce_outbound_rate_limit(
            connection,
            email="ADMIN@example.com",
            recipient_count=2,
            policy=policy,
            now=1000,
        )
        record_outbound_send(connection, email="ADMIN@example.com", recipient_count=2, now=1000)

        assert database.count_outbound_send_events(connection, email="admin@example.com", since=940) == (1, 2)


def test_outbound_policy_rejects_message_count_limit(tmp_path):
    path = tmp_path / "freemail.sqlite"
    database.initialize(str(path))
    with database.connect(str(path)) as connection:
        policy = OutboundRatePolicy(window_seconds=60, max_messages=1, max_recipients=10)
        record_outbound_send(connection, email="admin@example.com", recipient_count=1, now=1000)

        with pytest.raises(OutboundRateLimitExceeded, match="send rate limit"):
            enforce_outbound_rate_limit(
                connection,
                email="admin@example.com",
                recipient_count=1,
                policy=policy,
                now=1001,
            )


def test_outbound_policy_rejects_recipient_count_limit(tmp_path):
    path = tmp_path / "freemail.sqlite"
    database.initialize(str(path))
    with database.connect(str(path)) as connection:
        policy = OutboundRatePolicy(window_seconds=60, max_messages=10, max_recipients=2)
        record_outbound_send(connection, email="admin@example.com", recipient_count=1, now=1000)

        with pytest.raises(OutboundRateLimitExceeded, match="recipient rate limit"):
            enforce_outbound_rate_limit(
                connection,
                email="admin@example.com",
                recipient_count=2,
                policy=policy,
                now=1001,
            )


def test_outbound_policy_disabled_when_limits_are_zero(tmp_path):
    path = tmp_path / "freemail.sqlite"
    database.initialize(str(path))
    with database.connect(str(path)) as connection:
        policy = OutboundRatePolicy(window_seconds=60, max_messages=0, max_recipients=0)
        record_outbound_send(connection, email="admin@example.com", recipient_count=100, now=1000)

        enforce_outbound_rate_limit(
            connection,
            email="admin@example.com",
            recipient_count=100,
            policy=policy,
            now=1001,
        )
