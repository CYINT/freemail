from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from email.utils import formatdate
from email.utils import make_msgid
import imaplib
import smtplib
import ssl


@dataclass(frozen=True)
class SentMessage:
    message_id: str
    sender: str
    recipients: list[str]
    subject: str
    sent_folder: str = "Sent Items"
    sent_folder_saved: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class OutboundAttachment:
    filename: str
    content_type: str
    content_base64: str


def send_mailbox_message(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    recipients: list[str],
    subject: str,
    body: str,
    attachments: list[OutboundAttachment] | None = None,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
    imap_host: str | None = None,
    imap_port: int | None = None,
    sent_folder: str = "Sent Items",
) -> SentMessage:
    normalized_recipients = [recipient.strip() for recipient in recipients if recipient.strip()]
    message_id = make_msgid(domain=email.partition("@")[2] or None)
    message = _message(
        sender=email,
        recipients=normalized_recipients,
        subject=subject,
        body=body,
        attachments=attachments or [],
        message_id=message_id,
    )
    tls_context = _tls_context(verify_tls=verify_tls)
    with smtplib.SMTP_SSL(host, port, timeout=timeout_seconds, context=tls_context) as smtp:
        smtp.ehlo("freemail-webmail.local")
        smtp.login(email, password)
        refused = smtp.send_message(message)
    if refused:
        raise smtplib.SMTPRecipientsRefused(refused)
    sent_folder_saved = False
    if imap_host and imap_port:
        sent_folder_saved = _append_sent_message(
            email=email,
            password=password,
            host=imap_host,
            port=imap_port,
            folder=sent_folder,
            message=message,
            timeout_seconds=timeout_seconds,
            verify_tls=verify_tls,
        )
    return SentMessage(
        message_id=message_id,
        sender=email,
        recipients=normalized_recipients,
        subject=subject,
        sent_folder=sent_folder,
        sent_folder_saved=sent_folder_saved,
    )


def _message(
    *,
    sender: str,
    recipients: list[str],
    subject: str,
    body: str,
    attachments: list[OutboundAttachment] | None = None,
    message_id: str,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message.set_content(body)
    for attachment in attachments or []:
        maintype, _separator, subtype = attachment.content_type.partition("/")
        if not maintype or not subtype:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(
            base64.b64decode(attachment.content_base64, validate=True),
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
        )
    return message


def _tls_context(*, verify_tls: bool) -> ssl.SSLContext:
    if verify_tls:
        return ssl.create_default_context()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _append_sent_message(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str,
    message: EmailMessage,
    timeout_seconds: float,
    verify_tls: bool,
) -> bool:
    tls_context = _tls_context(verify_tls=verify_tls)
    try:
        with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
            imap.login(email, password)
            _ensure_imap_folder(imap, folder)
            status, _data = imap.append(f'"{folder}"', r"(\Seen)", formatdate(localtime=True), message.as_bytes())
            return status == "OK"
    except (OSError, imaplib.IMAP4.error):
        return False


def _ensure_imap_folder(imap: imaplib.IMAP4_SSL, folder: str) -> None:
    select_status, _data = imap.select(f'"{folder}"', readonly=True)
    if select_status == "OK":
        return
    create_status, _create_data = imap.create(f'"{folder}"')
    if create_status != "OK":
        raise imaplib.IMAP4.error(f"Mailbox sent folder could not be created: {folder}")
