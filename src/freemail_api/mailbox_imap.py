from __future__ import annotations

from dataclasses import asdict, dataclass
from email.utils import getaddresses
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
class MailboxAttachment:
    attachment_id: str
    filename: str
    content_type: str
    size: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MailboxAttachmentContent(MailboxAttachment):
    content: bytes


@dataclass(frozen=True)
class MailboxMessageDetail(MailboxMessage):
    body: str
    attachments: list[MailboxAttachment]


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


@dataclass(frozen=True)
class MailboxSearchResult:
    email: str
    folder: str
    query: str
    messages: list[MailboxMessage]

    def as_dict(self) -> dict[str, object]:
        return {
            "email": self.email,
            "folder": self.folder,
            "query": self.query,
            "messages": [message.as_dict() for message in self.messages],
        }


@dataclass(frozen=True)
class MailboxContact:
    name: str
    email: str
    message_count: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MailboxContacts:
    email: str
    folder: str
    contacts: list[MailboxContact]

    def as_dict(self) -> dict[str, object]:
        return {
            "email": self.email,
            "folder": self.folder,
            "contacts": [contact.as_dict() for contact in self.contacts],
        }


@dataclass(frozen=True)
class ArchivedMailboxMessage:
    folder: str
    message_id: str
    archive_folder: str
    archived: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MovedMailboxMessage:
    folder: str
    message_id: str
    target_folder: str
    moved: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MutatedMailboxFolder:
    folder: str
    action: str
    success: bool
    target_folder: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


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


def archive_mailbox_message(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str,
    message_id: str,
    archive_folder: str = "Archive",
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> ArchivedMailboxMessage:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        _move_message(imap, folder=folder, message_id=message_id, target_folder=archive_folder)
    return ArchivedMailboxMessage(
        folder=folder,
        message_id=message_id,
        archive_folder=archive_folder,
        archived=True,
    )


def move_mailbox_message(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str,
    message_id: str,
    target_folder: str,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> MovedMailboxMessage:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        _move_message(imap, folder=folder, message_id=message_id, target_folder=target_folder)
    return MovedMailboxMessage(folder=folder, message_id=message_id, target_folder=target_folder, moved=True)


def search_mailbox_messages(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str,
    query: str,
    limit: int = 25,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> MailboxSearchResult:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        messages = _search_messages(imap, folder=folder, query=query, limit=limit)
    return MailboxSearchResult(email=email, folder=folder, query=query, messages=messages)


def list_mailbox_contacts(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str = "INBOX",
    limit: int = 100,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> MailboxContacts:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        contacts = _list_contacts(imap, folder=folder, limit=limit)
    return MailboxContacts(email=email, folder=folder, contacts=contacts)


def get_mailbox_message(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str,
    message_id: str,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> MailboxMessageDetail:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        return _get_message(imap, folder=folder, message_id=message_id)


def get_mailbox_attachment(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str,
    message_id: str,
    attachment_id: str,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> MailboxAttachmentContent:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        return _get_attachment(imap, folder=folder, message_id=message_id, attachment_id=attachment_id)


def create_mailbox_folder(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> MutatedMailboxFolder:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        _create_folder(imap, folder)
    return MutatedMailboxFolder(folder=folder, action="create", success=True)


def rename_mailbox_folder(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str,
    target_folder: str,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> MutatedMailboxFolder:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        _rename_folder(imap, folder=folder, target_folder=target_folder)
    return MutatedMailboxFolder(folder=folder, target_folder=target_folder, action="rename", success=True)


def delete_mailbox_folder(
    *,
    email: str,
    password: str,
    host: str,
    port: int,
    folder: str,
    timeout_seconds: float = 10.0,
    verify_tls: bool = False,
) -> MutatedMailboxFolder:
    tls_context = _tls_context(verify_tls=verify_tls)
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context, timeout=timeout_seconds) as imap:
        imap.login(email, password)
        _delete_folder(imap, folder)
    return MutatedMailboxFolder(folder=folder, action="delete", success=True)


def _archive_message(imap: imaplib.IMAP4_SSL, *, folder: str, message_id: str, archive_folder: str) -> None:
    _move_message(imap, folder=folder, message_id=message_id, target_folder=archive_folder)


def _move_message(imap: imaplib.IMAP4_SSL, *, folder: str, message_id: str, target_folder: str) -> None:
    status, _data = imap.select(f'"{folder}"', readonly=False)
    if status != "OK":
        raise imaplib.IMAP4.error(f"Mailbox folder not found: {folder}")
    _ensure_folder(imap, target_folder)
    status, _data = imap.select(f'"{folder}"', readonly=False)
    if status != "OK":
        raise imaplib.IMAP4.error(f"Mailbox folder not found: {folder}")
    copy_status, _copy_data = imap.copy(message_id.encode("ascii"), f'"{target_folder}"')
    if copy_status != "OK":
        raise imaplib.IMAP4.error("Mailbox message could not be moved")
    store_status, _store_data = imap.store(message_id.encode("ascii"), "+FLAGS", r"(\Deleted)")
    if store_status != "OK":
        raise imaplib.IMAP4.error("Mailbox message could not be removed from source folder")
    expunge_status, _expunge_data = imap.expunge()
    if expunge_status != "OK":
        raise imaplib.IMAP4.error("Mailbox source folder expunge failed")


def _ensure_folder(imap: imaplib.IMAP4_SSL, folder: str) -> None:
    select_status, _data = imap.select(f'"{folder}"', readonly=True)
    if select_status == "OK":
        return
    _create_folder(imap, folder)


def _create_folder(imap: imaplib.IMAP4_SSL, folder: str) -> None:
    create_status, _create_data = imap.create(f'"{folder}"')
    if create_status != "OK":
        raise imaplib.IMAP4.error(f"Mailbox folder could not be created: {folder}")


def _rename_folder(imap: imaplib.IMAP4_SSL, *, folder: str, target_folder: str) -> None:
    rename_status, _rename_data = imap.rename(f'"{folder}"', f'"{target_folder}"')
    if rename_status != "OK":
        raise imaplib.IMAP4.error(f"Mailbox folder could not be renamed: {folder}")


def _delete_folder(imap: imaplib.IMAP4_SSL, folder: str) -> None:
    delete_status, _delete_data = imap.delete(f'"{folder}"')
    if delete_status != "OK":
        raise imaplib.IMAP4.error(f"Mailbox folder could not be deleted: {folder}")


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


def _search_messages(imap: imaplib.IMAP4_SSL, *, folder: str, query: str, limit: int) -> list[MailboxMessage]:
    clean_query = query.strip()
    if not clean_query:
        return []
    status, _data = imap.select(f'"{folder}"', readonly=True)
    if status != "OK":
        return []
    search_status, search_data = imap.search(None, *_search_criteria(clean_query))
    if search_status != "OK" or not search_data:
        return []
    message_ids = search_data[0].split()[-limit:]
    messages = []
    for message_id in reversed(message_ids):
        message = _message_header(imap, folder=folder, message_id=message_id)
        if message:
            messages.append(message)
    return messages


def _list_contacts(imap: imaplib.IMAP4_SSL, *, folder: str, limit: int) -> list[MailboxContact]:
    status, _data = imap.select(f'"{folder}"', readonly=True)
    if status != "OK":
        return []
    search_status, search_data = imap.search(None, "ALL")
    if search_status != "OK" or not search_data:
        return []
    contact_rows: dict[str, MailboxContact] = {}
    for message_id in search_data[0].split()[-limit:]:
        fetch_status, fetch_data = imap.fetch(message_id, "(BODY.PEEK[HEADER])")
        if fetch_status != "OK" or not fetch_data or not isinstance(fetch_data[0], tuple):
            continue
        header = BytesParser(policy=default).parsebytes(fetch_data[0][1])
        for name, address in _contacts_from_header(header):
            key = address.lower()
            current = contact_rows.get(key)
            if current:
                contact_rows[key] = MailboxContact(
                    name=current.name or name,
                    email=current.email,
                    message_count=current.message_count + 1,
                )
            else:
                contact_rows[key] = MailboxContact(name=name, email=address, message_count=1)
    return sorted(contact_rows.values(), key=lambda contact: (-contact.message_count, contact.email))


def _contacts_from_header(header) -> list[tuple[str, str]]:
    fields = [str(header.get(field, "")) for field in ("from", "reply-to", "to", "cc")]
    contacts = []
    for name, address in getaddresses(fields):
        clean_address = address.strip()
        if "@" not in clean_address:
            continue
        contacts.append((name.strip(), clean_address))
    return contacts


def _message_header(imap: imaplib.IMAP4_SSL, *, folder: str, message_id: bytes) -> MailboxMessage | None:
    fetch_status, fetch_data = imap.fetch(message_id, "(FLAGS BODY.PEEK[HEADER])")
    if fetch_status != "OK" or not fetch_data or not isinstance(fetch_data[0], tuple):
        return None
    header = BytesParser(policy=default).parsebytes(fetch_data[0][1])
    flags = _flags_from_fetch(fetch_data[0][0])
    return MailboxMessage(
        folder=folder,
        message_id=message_id.decode("ascii"),
        subject=str(header.get("subject", "")),
        sender=str(header.get("from", "")),
        recipients=str(header.get("to", "")),
        date=str(header.get("date", "")),
        unread="\\Seen" not in flags,
    )


def _search_criteria(query: str) -> tuple[str, ...]:
    quoted_query = _quote_search_value(query)
    return (
        "OR",
        "OR",
        "OR",
        "FROM",
        quoted_query,
        "TO",
        quoted_query,
        "SUBJECT",
        quoted_query,
        "BODY",
        quoted_query,
    )


def _quote_search_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', r"\"")
    return f'"{escaped}"'


def _get_message(imap: imaplib.IMAP4_SSL, *, folder: str, message_id: str) -> MailboxMessageDetail:
    status, _data = imap.select(f'"{folder}"', readonly=True)
    if status != "OK":
        raise imaplib.IMAP4.error(f"Mailbox folder not found: {folder}")
    fetch_status, fetch_data = imap.fetch(message_id.encode("ascii"), "(FLAGS BODY.PEEK[])")
    if fetch_status != "OK" or not fetch_data or not isinstance(fetch_data[0], tuple):
        raise imaplib.IMAP4.error("Mailbox message not found")
    parsed = BytesParser(policy=default).parsebytes(fetch_data[0][1])
    flags = _flags_from_fetch(fetch_data[0][0])
    return MailboxMessageDetail(
        folder=folder,
        message_id=message_id,
        subject=str(parsed.get("subject", "")),
        sender=str(parsed.get("from", "")),
        recipients=str(parsed.get("to", "")),
        date=str(parsed.get("date", "")),
        unread="\\Seen" not in flags,
        body=_body_from_message(parsed),
        attachments=_attachments_from_message(parsed),
    )


def _get_attachment(
    imap: imaplib.IMAP4_SSL,
    *,
    folder: str,
    message_id: str,
    attachment_id: str,
) -> MailboxAttachmentContent:
    status, _data = imap.select(f'"{folder}"', readonly=True)
    if status != "OK":
        raise imaplib.IMAP4.error(f"Mailbox folder not found: {folder}")
    fetch_status, fetch_data = imap.fetch(message_id.encode("ascii"), "(BODY.PEEK[])")
    if fetch_status != "OK" or not fetch_data or not isinstance(fetch_data[0], tuple):
        raise imaplib.IMAP4.error("Mailbox message not found")
    parsed = BytesParser(policy=default).parsebytes(fetch_data[0][1])
    for attachment in _attachment_contents_from_message(parsed):
        if attachment.attachment_id == attachment_id:
            return attachment
    raise imaplib.IMAP4.error("Mailbox attachment not found")


def _body_from_message(message) -> str:
    if message.is_multipart():
        plain_parts = []
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            disposition = part.get_content_disposition()
            if disposition == "attachment":
                continue
            if part.get_content_type() == "text/plain":
                plain_parts.append(str(part.get_content()))
        if plain_parts:
            return "\n".join(part.strip() for part in plain_parts if part.strip())
        return ""
    content = message.get_content()
    return str(content).strip()


def _attachments_from_message(message) -> list[MailboxAttachment]:
    return [
        MailboxAttachment(
            attachment_id=attachment.attachment_id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            size=attachment.size,
        )
        for attachment in _attachment_contents_from_message(message)
    ]


def _attachment_contents_from_message(message) -> list[MailboxAttachmentContent]:
    if not message.is_multipart():
        return []
    attachments = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if not _is_attachment_part(part):
            continue
        content = part.get_payload(decode=True) or b""
        attachments.append(
            MailboxAttachmentContent(
                attachment_id=str(len(attachments)),
                filename=part.get_filename() or f"attachment-{len(attachments) + 1}",
                content_type=part.get_content_type() or "application/octet-stream",
                size=len(content),
                content=content,
            )
        )
    return attachments


def _is_attachment_part(part) -> bool:
    return part.get_content_disposition() == "attachment" or bool(part.get_filename())


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
