import pytest

from freemail_api.attachment_policy import AttachmentPolicy
from freemail_api.attachment_policy import AttachmentPolicyError
from freemail_api.attachment_policy import parse_allowed_content_types
from freemail_api.attachment_policy import validate_attachments
from freemail_api.schemas import MailboxSendAttachmentCreate


def test_parse_allowed_content_types_normalizes_values():
    assert parse_allowed_content_types(" text/plain,Application/PDF, ") == frozenset({"text/plain", "application/pdf"})


def test_validate_attachments_accepts_allowed_bounded_attachment():
    validate_attachments(
        [MailboxSendAttachmentCreate(filename="note.txt", contentType="text/plain", contentBase64="bm90ZQ==")],
        AttachmentPolicy(max_bytes=10, allowed_content_types=frozenset({"text/plain"})),
    )


def test_validate_attachments_rejects_unsupported_content_type():
    with pytest.raises(AttachmentPolicyError, match="Unsupported attachment content type"):
        validate_attachments(
            [MailboxSendAttachmentCreate(filename="data.bin", contentType="application/octet-stream", contentBase64="AA==")],
            AttachmentPolicy(max_bytes=10, allowed_content_types=frozenset({"text/plain"})),
        )


def test_validate_attachments_rejects_oversized_content():
    with pytest.raises(AttachmentPolicyError, match="exceeds 3 bytes"):
        validate_attachments(
            [MailboxSendAttachmentCreate(filename="note.txt", contentType="text/plain", contentBase64="bm90ZQ==")],
            AttachmentPolicy(max_bytes=3, allowed_content_types=frozenset({"text/plain"})),
        )


def test_validate_attachments_rejects_invalid_base64():
    with pytest.raises(AttachmentPolicyError, match="Invalid attachment payload"):
        validate_attachments(
            [MailboxSendAttachmentCreate(filename="note.txt", contentType="text/plain", contentBase64="not-base64")],
            AttachmentPolicy(max_bytes=10, allowed_content_types=frozenset({"text/plain"})),
        )
