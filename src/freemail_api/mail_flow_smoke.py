from __future__ import annotations

import imaplib
import re
import smtplib
import ssl
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import EmailMessage


@dataclass(frozen=True)
class LocatedMessage:
    folder: str
    message_ids: list[str]


@dataclass(frozen=True)
class MailFlowResult:
    inbound_accepted: bool
    inbound_found: LocatedMessage | None
    submission_accepted: bool
    submission_found: LocatedMessage | None
    submission_dkim_domains: list[str]
    required_dkim_domain: str
    marker: str
    checked_at: str

    @property
    def passed(self) -> bool:
        return bool(
            self.inbound_accepted
            and self.inbound_found
            and self.submission_accepted
            and self.submission_found
            and self.required_dkim_domain in self.submission_dkim_domains
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "marker": self.marker,
            "inboundAccepted": self.inbound_accepted,
            "inboundFound": asdict(self.inbound_found) if self.inbound_found else None,
            "submissionAccepted": self.submission_accepted,
            "submissionFound": asdict(self.submission_found) if self.submission_found else None,
            "submissionDkimDomains": self.submission_dkim_domains,
            "requiredDkimDomain": self.required_dkim_domain,
            "checkedAt": self.checked_at,
        }


def run_mail_flow_smoke(
    *,
    email: str,
    password: str,
    host: str,
    smtp_port: int,
    submission_port: int,
    imap_port: int,
    inbound_recipient: str,
    inbound_sender: str,
    submission_recipient: str,
    required_dkim_domain: str | None = None,
    timeout_seconds: float = 10.0,
    poll_attempts: int = 10,
    poll_interval_seconds: float = 1.0,
    verify_tls: bool = False,
) -> MailFlowResult:
    marker = str(int(time.time()))
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    tls_context = _tls_context(verify_tls=verify_tls)
    inbound_subject = f"FreeMail inbound smoke {marker}"
    submission_subject = f"FreeMail submission smoke {marker}"
    required_dkim_domain = (required_dkim_domain or email.partition("@")[2]).lower()

    inbound_accepted = _send_inbound_message(
        host=host,
        port=smtp_port,
        sender=inbound_sender,
        recipient=inbound_recipient,
        subject=inbound_subject,
        body=f"inbound smoke {marker}",
        timeout_seconds=timeout_seconds,
    )
    submission_accepted = _send_submission_message(
        host=host,
        port=submission_port,
        email=email,
        password=password,
        recipient=submission_recipient,
        subject=submission_subject,
        body=f"submission smoke {marker}",
        timeout_seconds=timeout_seconds,
        tls_context=tls_context,
    )

    inbound_found = None
    submission_found = None
    submission_dkim_domains: list[str] = []
    for _attempt in range(poll_attempts):
        folders = _list_folders(
            host=host,
            port=imap_port,
            email=email,
            password=password,
            timeout_seconds=timeout_seconds,
            tls_context=tls_context,
        )
        inbound_found = inbound_found or _find_subject(
            host=host,
            port=imap_port,
            email=email,
            password=password,
            folders=folders,
            subject=inbound_subject,
            timeout_seconds=timeout_seconds,
            tls_context=tls_context,
        )
        submission_found = submission_found or _find_subject(
            host=host,
            port=imap_port,
            email=email,
            password=password,
            folders=folders,
            subject=submission_subject,
            timeout_seconds=timeout_seconds,
            tls_context=tls_context,
        )
        if submission_found and not submission_dkim_domains:
            submission_dkim_domains = _fetch_dkim_domains(
                host=host,
                port=imap_port,
                email=email,
                password=password,
                located_message=submission_found,
                timeout_seconds=timeout_seconds,
                tls_context=tls_context,
            )
        if inbound_found and submission_found and submission_dkim_domains:
            break
        time.sleep(poll_interval_seconds)

    return MailFlowResult(
        inbound_accepted=inbound_accepted,
        inbound_found=inbound_found,
        submission_accepted=submission_accepted,
        submission_found=submission_found,
        submission_dkim_domains=submission_dkim_domains,
        required_dkim_domain=required_dkim_domain,
        marker=marker,
        checked_at=checked_at,
    )


def _send_inbound_message(
    *,
    host: str,
    port: int,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    timeout_seconds: float,
) -> bool:
    message = _message(sender=sender, recipient=recipient, subject=subject, body=body)
    with smtplib.SMTP(host, port, timeout=timeout_seconds) as smtp:
        smtp.ehlo("freemail-smoke.local")
        refused = smtp.send_message(message)
    return not refused


def _send_submission_message(
    *,
    host: str,
    port: int,
    email: str,
    password: str,
    recipient: str,
    subject: str,
    body: str,
    timeout_seconds: float,
    tls_context: ssl.SSLContext,
) -> bool:
    message = _message(sender=email, recipient=recipient, subject=subject, body=body)
    with smtplib.SMTP_SSL(host, port, timeout=timeout_seconds, context=tls_context) as smtp:
        smtp.ehlo("freemail-smoke.local")
        smtp.login(email, password)
        refused = smtp.send_message(message)
    return not refused


def _message(*, sender: str, recipient: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    return message


def _list_folders(
    *,
    host: str,
    port: int,
    email: str,
    password: str,
    timeout_seconds: float,
    tls_context: ssl.SSLContext,
) -> list[str]:
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        status, rows = imap.list()
    if status != "OK" or not rows:
        return ["INBOX"]
    folders = [_parse_folder(row.decode("utf-8", errors="replace")) for row in rows]
    return [folder for folder in folders if folder]


def _find_subject(
    *,
    host: str,
    port: int,
    email: str,
    password: str,
    folders: list[str],
    subject: str,
    timeout_seconds: float,
    tls_context: ssl.SSLContext,
) -> LocatedMessage | None:
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        for folder in folders:
            status, _data = imap.select(f'"{folder}"', readonly=True)
            if status != "OK":
                continue
            search_status, search_data = imap.search(None, "SUBJECT", f'"{subject}"')
            if search_status == "OK" and search_data:
                ids = [message_id.decode("ascii") for message_id in search_data[0].split()]
                if ids:
                    return LocatedMessage(folder=folder, message_ids=ids)
    return None


def _fetch_dkim_domains(
    *,
    host: str,
    port: int,
    email: str,
    password: str,
    located_message: LocatedMessage,
    timeout_seconds: float,
    tls_context: ssl.SSLContext,
) -> list[str]:
    message_id = located_message.message_ids[-1]
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        status, _data = imap.select(f'"{located_message.folder}"', readonly=True)
        if status != "OK":
            return []
        fetch_status, fetch_data = imap.fetch(message_id, "(BODY.PEEK[HEADER])")
    if fetch_status != "OK" or not fetch_data or not isinstance(fetch_data[0], tuple):
        return []
    header = fetch_data[0][1].decode("utf-8", errors="replace")
    return _dkim_domains_from_header(header)


def _dkim_domains_from_header(header: str) -> list[str]:
    domains = []
    for line in header.splitlines():
        if line.lower().startswith("dkim-signature:"):
            match = re.search(r"(?:^|;)\s*d=([^;\s]+)", line, flags=re.IGNORECASE)
            if match and match.group(1).lower() not in domains:
                domains.append(match.group(1).lower())
    return domains


def _parse_folder(row: str) -> str:
    _metadata, _separator, folder = row.rpartition(' "/" ')
    return folder.strip('"')


def _tls_context(*, verify_tls: bool) -> ssl.SSLContext:
    if verify_tls:
        return ssl.create_default_context()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context
