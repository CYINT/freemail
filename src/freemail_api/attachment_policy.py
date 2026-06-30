from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Protocol


class AttachmentLike(Protocol):
    filename: str
    content_type: str
    content_base64: str


@dataclass(frozen=True)
class AttachmentPolicy:
    max_bytes: int
    allowed_content_types: frozenset[str]


class AttachmentPolicyError(ValueError):
    pass


def parse_allowed_content_types(value: str) -> frozenset[str]:
    return frozenset(content_type.strip().lower() for content_type in value.split(",") if content_type.strip())


def validate_attachments(attachments: list[AttachmentLike], policy: AttachmentPolicy) -> None:
    for attachment in attachments:
        content_type = attachment.content_type.lower()
        if content_type not in policy.allowed_content_types:
            raise AttachmentPolicyError(f"Unsupported attachment content type: {attachment.content_type}")
        try:
            content = base64.b64decode(attachment.content_base64, validate=True)
        except binascii.Error as error:
            raise AttachmentPolicyError("Invalid attachment payload") from error
        if len(content) > policy.max_bytes:
            raise AttachmentPolicyError(f"Attachment exceeds {policy.max_bytes} bytes: {attachment.filename}")
