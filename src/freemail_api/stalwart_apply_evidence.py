from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any, Callable

from .mail_core import probe_mail_core
from .stalwart_plan import PlanOptions, build_apply_plan, build_apply_plan_status
from .stalwart_queue import query_queue_with_cli


Runner = Callable[..., subprocess.CompletedProcess[str]]
QueueQuery = Callable[..., Any]
MailCoreProbe = Callable[..., dict[str, object]]


@dataclass(frozen=True)
class StalwartApplyEvidenceOptions:
    domain: str
    user_secrets: dict[str, str]
    applied_by: str = ""
    image: str = "ghcr.io/stalwartlabs/cli"
    queue_image: str = "ghcr.io/stalwartlabs/cli"
    timeout_seconds: int = 60
    mail_core_host: str = "127.0.0.1"
    smtp_port: int = 2525
    submission_port: int = 2465
    imap_port: int = 2993
    jmap_port: int = 18092
    now: datetime | None = None


def collect_stalwart_apply_evidence(
    connection: sqlite3.Connection,
    options: StalwartApplyEvidenceOptions,
    *,
    runner: Runner = subprocess.run,
    queue_query: QueueQuery = query_queue_with_cli,
    mail_core_probe: MailCoreProbe = probe_mail_core,
) -> dict[str, Any]:
    normalized_secrets = {email.lower(): secret for email, secret in options.user_secrets.items()}
    plan_status = build_apply_plan_status(connection, set(normalized_secrets))
    plan = build_apply_plan(connection, PlanOptions(user_secrets=normalized_secrets))
    plan_ndjson = _format_ndjson(plan)
    completed = runner(
        _apply_command(options.image),
        input=plan_ndjson,
        check=False,
        capture_output=True,
        text=True,
        timeout=options.timeout_seconds,
    )
    readiness = mail_core_probe(
        options.mail_core_host,
        options.smtp_port,
        options.submission_port,
        options.imap_port,
        options.jmap_port,
    )
    queue_summary = queue_query(image=options.queue_image, timeout_seconds=options.timeout_seconds)
    queue_clear = bool(getattr(queue_summary, "clear", False))
    applied_at = options.now or datetime.now(UTC)
    return {
        "applied": completed.returncode == 0,
        "appliedAt": _format_timestamp(applied_at),
        "appliedBy": options.applied_by,
        "domain": options.domain,
        "applyTool": "stalwart-cli apply --stdin",
        "planStatus": plan_status,
        "result": {
            "exitCode": completed.returncode,
            "stdoutSha256": _sha256_text(completed.stdout),
            "stderrSha256": _sha256_text(completed.stderr),
            "planInputSha256": _sha256_text(plan_ndjson),
            "operationCounts": _operation_counts(plan),
        },
        "postApplyReadiness": {
            "mailCoreReady": readiness.get("protocolReady") is True,
            "queueClear": queue_clear,
        },
    }


def load_user_secrets(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("secrets JSON must be an object mapping email addresses to secrets")
    return {str(key).lower(): str(value) for key, value in data.items()}


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _apply_command(image: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "-e",
        "STALWART_URL",
        "-e",
        "STALWART_USER",
        "-e",
        "STALWART_PASSWORD",
        image,
        "apply",
        "--stdin",
    ]


def _format_ndjson(plan: list[dict[str, object]]) -> str:
    if not plan:
        return ""
    return "\n".join(json.dumps(operation, sort_keys=True) for operation in plan) + "\n"


def _operation_counts(plan: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for operation in plan:
        object_name = str(operation.get("object", ""))
        values = operation.get("value")
        if object_name and isinstance(values, dict):
            counts[object_name] = counts.get(object_name, 0) + len(values)
    return counts


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
