from __future__ import annotations

from dataclasses import asdict, dataclass
from email.parser import BytesParser
from email.policy import default
import imaplib
import ssl


@dataclass(frozen=True)
class MailboxMessage:
    folder: str
    message_id: str
    subject: str
    sender: str
    recipients: str
    date: str
    unread: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MailboxFolder:
    name: str
    message_count: int
    unread_count: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MailboxSnapshot:
    email: str
    folders: list[MailboxFolder]
    messages: list[MailboxMessage]

    def as_dict(self) -> dict[str, object]:
        return {
            "email": self.email,
            "folders": [folder.as_dict() for folder in self.folders],
            "messages": [message.as_dict() for message in self.messages],
        }


def list_mailbox_snapshot(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str = "INBOX",
    limit: int = 25,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> MailboxSnapshot:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        folders = _list_folders(imap)
        messages = _list_messages(imap, folder=folder, limit=limit)
    return MailboxSnapshot(email=email, folders=folders, messages=messages)


def _list_folders(imap: imaplib.IMAP4_SSL) -> list[MailboxFolder]:
    status, rows = imap.list()
    if status != "OK" or not rows:
        return []

    folders = []
    for row in rows:
        name = _parse_folder(row.decode("utf-8", errors="replace"))
        if not name:
            continue
        select_status, count_data = imap.select(f'"{name}"', readonly=True)
        if select_status != "OK":
            continue
        message_count = _count_from_select(count_data)
        search_status, unread_data = imap.search(None, "UNSEEN")
        unread_count = len(unread_data[0].split()) if search_status == "OK" and unread_data else 0
        folders.append(MailboxFolder(name=name, message_count=message_count, unread_count=unread_count))
    return folders


def _list_messages(imap: imaplib.IMAP4_SSL, *, folder: str, limit: int) -> list[MailboxMessage]:
    status, _data = imap.select(f'"{folder}"', readonly=True)
    if status != "OK":
        return []
    search_status, search_data = imap.search(None, "ALL")
    if search_status != "OK" or not search_data:
        return []
    message_ids = search_data[0].split()[-limit:]
    messages = []
    for message_id in reversed(message_ids):
        fetch_status, fetch_data = imap.fetch(message_id, "(FLAGS BODY.PEEK[HEADER])")
        if fetch_status != "OK" or not fetch_data or not isinstance(fetch_data[0], tuple):
            continue
        header = BytesParser(policy=default).parsebytes(fetch_data[0][1])
        flags = _flags_from_fetch(fetch_data[0][0])
        messages.append(
            MailboxMessage(
                folder=folder,
                message_id=message_id.decode("ascii"),
                subject=str(header.get("subject", "")),
                sender=str(header.get("from", "")),
                recipients=str(header.get("to", "")),
                date=str(header.get("date", "")),
                unread="\\Seen" not in flags,
            )
        )
    return messages


def _count_from_select(data: list[bytes] | None) -> int:
    if not data:
        return 0
    try:
        return int(data[0])
    except (TypeError, ValueError):
        return 0


def _flags_from_fetch(fetch_prefix: bytes) -> set[str]:
    text = fetch_prefix.decode("utf-8", errors="replace")
    marker = "FLAGS ("
    if marker not in text:
        return set()
    flag_text = text.split(marker, 1)[1].split(")", 1)[0]
    return set(flag_text.split())


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
