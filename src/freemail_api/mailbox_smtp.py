from __future__ import annotations

from dataclasses import asdict, dataclass
from email.message import EmailMessage
from email.utils import make_msgid
import smtplib
import ssl


@dataclass(frozen=True)
class SentMessage:
    message_id: str
    sender: str
    recipients: list[str]
    subject: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def send_mailbox_message(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    recipients: list[str],
    subject: str,
    body: str,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> SentMessage:
    normalized_recipients = [recipient.strip() for recipient in recipients if recipient.strip()]
    message_id = make_msgid(domain=email.partition("@")[2] or None)
    message = _message(
        sender=email,
        recipients=normalized_recipients,
        subject=subject,
        body=body,
        message_id=message_id,
    )
    tls_context = _tls_context(verify_tls=verify_tls)
    with smtplib.SMTP_SSL(host, port, timeout=timeout_seconds, context=tls_context) as smtp:
        smtp.ehlo("freemail-webmail.local")
        smtp.login(email, password)
        refused = smtp.send_message(message)
    if refused:
        raise smtplib.SMTPRecipientsRefused(refused)
    return SentMessage(message_id=message_id, sender=email, recipients=normalized_recipients, subject=subject)


def _message(
    *,
    sender: str,
    recipients: list[str],
    subject: str,
    body: str,
    message_id: str,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message.set_content(body)
    return message


def _tls_context(*, verify_tls: bool) -> ssl.SSLContext:
    if verify_tls:
        return ssl.create_default_context()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context
