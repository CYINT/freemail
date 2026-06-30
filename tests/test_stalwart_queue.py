from datetime import UTC, datetime

import pytest

from freemail_api.stalwart_queue import parse_queue_ndjson, summarize_queue


def test_parse_queue_ndjson_accepts_empty_output():
    assert parse_queue_ndjson("") == []


def test_parse_queue_ndjson_parses_message_objects():
    messages = parse_queue_ndjson('{"id":"q1","nextRetry":"2026-06-30T01:00:00Z"}\n')

    assert messages == [{"id": "q1", "nextRetry": "2026-06-30T01:00:00Z"}]


def test_parse_queue_ndjson_rejects_non_object_lines():
    with pytest.raises(ValueError):
        parse_queue_ndjson('["not-an-object"]\n')


def test_summarize_queue_counts_due_messages():
    summary = summarize_queue(
        [
            {"id": "due", "nextRetry": "2026-06-30T00:59:00Z"},
            {"id": "future", "nextRetry": "2026-06-30T02:00:00Z"},
            {"id": "unset", "nextRetry": None},
        ],
        now=datetime(2026, 6, 30, 1, 0, tzinfo=UTC),
    )

    assert summary.clear is False
    assert summary.pending_count == 3
    assert summary.due_count == 1
    assert summary.as_dict()["passed"] is False
    assert summary.as_dict()["pending"] == 3
    assert summary.as_dict()["due"] == 1
    assert summary.as_dict()["pendingCount"] == 3
    assert summary.as_dict()["dueCount"] == 1
    assert summary.as_dict()["reviewedAt"] == "2026-06-30T01:00:00Z"


def test_summarize_queue_marks_empty_queue_as_passed():
    summary = summarize_queue([], now=datetime(2026, 6, 30, 1, 0, tzinfo=UTC))

    assert summary.clear is True
    assert summary.as_dict()["passed"] is True
    assert summary.as_dict()["pending"] == 0
    assert summary.as_dict()["due"] == 0
