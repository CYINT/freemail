from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class QueueSummary:
    pending_count: int
    due_count: int
    messages: list[dict[str, Any]]

    @property
    def clear(self) -> bool:
        return self.pending_count == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "clear": self.clear,
            "pendingCount": self.pending_count,
            "dueCount": self.due_count,
            "messages": self.messages,
        }


def query_queue_with_cli(
    *,
    image: str = "ghcr.io/stalwartlabs/cli",
    timeout_seconds: int = 30,
) -> QueueSummary:
    command = [
        "docker",
        "run",
        "--rm",
        "-e",
        "STALWART_URL",
        "-e",
        "STALWART_USER",
        "-e",
        "STALWART_PASSWORD",
        image,
        "query",
        "QueuedMessage",
        "--fields",
        "id,returnPath,recipients,receivedViaPort,nextRetry,createdAt",
        "--json",
        "--no-color",
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return summarize_queue(parse_queue_ndjson(completed.stdout))


def parse_queue_ndjson(output: str) -> list[dict[str, Any]]:
    messages = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped:
            data = json.loads(stripped)
            if isinstance(data, dict):
                messages.append(data)
            else:
                raise ValueError("QueuedMessage output line must be a JSON object")
    return messages


def summarize_queue(messages: list[dict[str, Any]], now: datetime | None = None) -> QueueSummary:
    current_time = now or datetime.now(UTC)
    due_count = sum(1 for message in messages if _is_due(message.get("nextRetry"), current_time))
    return QueueSummary(pending_count=len(messages), due_count=due_count, messages=messages)


def _is_due(next_retry: object, now: datetime) -> bool:
    if not isinstance(next_retry, str) or not next_retry:
        return False
    try:
        retry_at = datetime.fromisoformat(next_retry.replace("Z", "+00:00"))
    except ValueError:
        return False
    return retry_at <= now
