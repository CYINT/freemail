from email.message import EmailMessage

from freemail_api.mailbox_imap import (
    ArchivedMailboxMessage,
    MailboxAttachment,
    MailboxFolder,
    MailboxMessage,
    MailboxSearchResult,
    MailboxMessageDetail,
    MovedMailboxMessage,
    MailboxSnapshot,
    _archive_message,
    _attachment_contents_from_message,
    _attachments_from_message,
    _body_from_message,
    _count_from_select,
    _ensure_folder,
    _flags_from_fetch,
    _get_attachment,
    _get_message,
    _list_folders,
    _list_messages,
    _move_message,
    _parse_folder,
    _quote_search_value,
    _search_criteria,
    _search_messages,
    _tls_context,
)


class FakeImap:
    def __init__(self):
        self.selected_folders = []
        self.created_folders = []
        self.copied_messages = []
        self.stored_flags = []
        self.expunge_called = False
        self.search_calls = []

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent Items"']

    def select(self, folder, readonly=True):
        self.selected_folder = folder
        self.selected_folders.append((folder, readonly))
        return "OK", [b"3"]

    def search(self, charset, *criteria):
        self.search_calls.append((charset, criteria))
        if criteria == ("UNSEEN",):
            return "OK", [b"1 3"]
        return "OK", [b"1 2 3"]

    def fetch(self, message_id, query):
        body = b"Body text\r\n"
        headers = (
            b"Subject: Hello\r\n"
            b"From: sender@example.com\r\n"
            b"To: admin@example.com\r\n"
            b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
            b"\r\n"
        )
        payload = headers + body if "BODY.PEEK[]" in query else headers
        prefix = b"3 (FLAGS (\\Seen) BODY[HEADER] {%d}" % len(payload)
        return "OK", [(prefix, payload)]

    def create(self, folder):
        self.created_folders.append(folder)
        return "OK", []

    def copy(self, message_id, folder):
        self.copied_messages.append((message_id, folder))
        return "OK", []

    def store(self, message_id, command, flags):
        self.stored_flags.append((message_id, command, flags))
        return "OK", []

    def expunge(self):
        self.expunge_called = True
        return "OK", []


def test_parse_folder_extracts_folder_name():
    assert _parse_folder('(\\Sent) "/" "Sent Items"') == "Sent Items"


def test_snapshot_serializes_nested_records():
    snapshot = MailboxSnapshot(
        email="admin@example.com",
        folders=[MailboxFolder(name="INBOX", message_count=1, unread_count=0)],
        messages=[
            MailboxMessage(
                folder="INBOX",
                message_id="1",
                subject="Hello",
                sender="sender@example.com",
                recipients="admin@example.com",
                date="Mon, 01 Jan 2024 00:00:00 +0000",
                unread=False,
            )
        ],
    )

    assert snapshot.as_dict() == {
        "email": "admin@example.com",
        "folders": [{"name": "INBOX", "message_count": 1, "unread_count": 0}],
        "messages": [
            {
                "folder": "INBOX",
                "message_id": "1",
                "subject": "Hello",
                "sender": "sender@example.com",
                "recipients": "admin@example.com",
                "date": "Mon, 01 Jan 2024 00:00:00 +0000",
                "unread": False,
            }
        ],
    }


def test_message_detail_serializes_body():
    detail = MailboxMessageDetail(
        folder="INBOX",
        message_id="1",
        subject="Hello",
        sender="sender@example.com",
        recipients="admin@example.com",
        date="Mon, 01 Jan 2024 00:00:00 +0000",
        unread=False,
        body="Body text",
        attachments=[MailboxAttachment("0", "report.txt", "text/plain", 6)],
    )

    assert detail.as_dict()["body"] == "Body text"
    assert detail.as_dict()["attachments"][0]["filename"] == "report.txt"


def test_search_result_serializes_messages():
    result = MailboxSearchResult(
        email="admin@example.com",
        folder="INBOX",
        query="hello",
        messages=[
            MailboxMessage(
                folder="INBOX",
                message_id="1",
                subject="Hello",
                sender="sender@example.com",
                recipients="admin@example.com",
                date="Mon, 01 Jan 2024 00:00:00 +0000",
                unread=False,
            )
        ],
    )

    assert result.as_dict()["query"] == "hello"
    assert result.as_dict()["messages"][0]["subject"] == "Hello"


def test_archived_message_serializes_archive_result():
    archived = ArchivedMailboxMessage(folder="INBOX", message_id="7", archive_folder="Archive", archived=True)

    assert archived.as_dict() == {
        "folder": "INBOX",
        "message_id": "7",
        "archive_folder": "Archive",
        "archived": True,
    }


def test_moved_message_serializes_move_result():
    moved = MovedMailboxMessage(folder="INBOX", message_id="7", target_folder="Deleted Items", moved=True)

    assert moved.as_dict() == {
        "folder": "INBOX",
        "message_id": "7",
        "target_folder": "Deleted Items",
        "moved": True,
    }


def test_list_folders_counts_messages_and_unread():
    folders = _list_folders(FakeImap())

    assert [folder.name for folder in folders] == ["INBOX", "Sent Items"]
    assert folders[0].message_count == 3
    assert folders[0].unread_count == 2


def test_list_messages_parses_headers_and_seen_flag():
    messages = _list_messages(FakeImap(), folder="INBOX", limit=1)

    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].sender == "sender@example.com"
    assert messages[0].recipients == "admin@example.com"
    assert messages[0].unread is False


def test_search_messages_uses_sender_recipient_subject_and_body_criteria():
    imap = FakeImap()

    messages = _search_messages(imap, folder="INBOX", query="hello", limit=2)

    assert len(messages) == 2
    assert messages[0].subject == "Hello"
    assert imap.search_calls[-1] == (None, _search_criteria("hello"))


def test_search_messages_returns_empty_for_blank_query():
    assert _search_messages(FakeImap(), folder="INBOX", query=" ", limit=10) == []


def test_search_criteria_covers_expected_fields():
    criteria = _search_criteria("needle")

    assert criteria.count("OR") == 3
    assert ("FROM", '"needle"') == criteria[3:5]
    assert ("TO", '"needle"') == criteria[5:7]
    assert ("SUBJECT", '"needle"') == criteria[7:9]
    assert ("BODY", '"needle"') == criteria[9:11]


def test_quote_search_value_escapes_special_characters():
    assert _quote_search_value('hello "quoted" \\ path') == r'"hello \"quoted\" \\ path"'


def test_get_message_parses_body_and_headers():
    message = _get_message(FakeImap(), folder="INBOX", message_id="3")

    assert message.subject == "Hello"
    assert message.body == "Body text"
    assert message.unread is False
    assert message.attachments == []


def test_attachment_summaries_extract_attachment_parts():
    message = EmailMessage()
    message.set_content("Plain body")
    message.add_attachment(b"report", maintype="text", subtype="plain", filename="report.txt")

    attachments = _attachments_from_message(message)

    assert attachments == [MailboxAttachment("0", "report.txt", "text/plain", 6)]


def test_attachment_contents_extract_download_bytes():
    message = EmailMessage()
    message.set_content("Plain body")
    message.add_attachment(b"report", maintype="text", subtype="plain", filename="report.txt")

    attachment = _attachment_contents_from_message(message)[0]

    assert attachment.attachment_id == "0"
    assert attachment.filename == "report.txt"
    assert attachment.content == b"report"


def test_get_attachment_returns_selected_attachment():
    class AttachmentImap(FakeImap):
        def fetch(self, message_id, query):
            message = EmailMessage()
            message.set_content("Plain body")
            message.add_attachment(b"report", maintype="text", subtype="plain", filename="report.txt")
            payload = message.as_bytes()
            prefix = b"3 (BODY[] {%d}" % len(payload)
            return "OK", [(prefix, payload)]

    attachment = _get_attachment(AttachmentImap(), folder="INBOX", message_id="3", attachment_id="0")

    assert attachment.filename == "report.txt"
    assert attachment.content == b"report"


def test_archive_message_copies_marks_deleted_and_expunges():
    imap = FakeImap()

    _archive_message(imap, folder="INBOX", message_id="3", archive_folder="Archive")

    assert imap.selected_folders == [('"INBOX"', False), ('"Archive"', True), ('"INBOX"', False)]
    assert imap.copied_messages == [(b"3", '"Archive"')]
    assert imap.stored_flags == [(b"3", "+FLAGS", r"(\Deleted)")]
    assert imap.expunge_called is True


def test_move_message_copies_to_target_marks_deleted_and_expunges():
    imap = FakeImap()

    _move_message(imap, folder="INBOX", message_id="4", target_folder="Deleted Items")

    assert imap.selected_folders == [('"INBOX"', False), ('"Deleted Items"', True), ('"INBOX"', False)]
    assert imap.copied_messages == [(b"4", '"Deleted Items"')]
    assert imap.stored_flags == [(b"4", "+FLAGS", r"(\Deleted)")]
    assert imap.expunge_called is True


def test_ensure_folder_creates_missing_archive_folder():
    class MissingFolderImap(FakeImap):
        def select(self, folder, readonly=True):
            self.selected_folder = folder
            return ("NO", []) if folder == '"Archive"' else ("OK", [b"1"])

    imap = MissingFolderImap()

    _ensure_folder(imap, "Archive")

    assert imap.created_folders == ['"Archive"']


def test_body_from_message_prefers_plain_text_part():
    message = EmailMessage()
    message.set_content("Plain body")
    message.add_alternative("<p>HTML body</p>", subtype="html")

    assert _body_from_message(message) == "Plain body"


def test_count_from_select_handles_invalid_data():
    assert _count_from_select([b"12"]) == 12
    assert _count_from_select([b"not-a-number"]) == 0
    assert _count_from_select(None) == 0


def test_flags_from_fetch_extracts_seen_flag():
    flags = _flags_from_fetch(b"1 (FLAGS (\\Seen custom) BODY[HEADER] {10}")

    assert "\\Seen" in flags
    assert "custom" in flags


def test_flags_from_fetch_handles_missing_marker():
    assert _flags_from_fetch(b"1 BODY[HEADER] {10}") == set()


def test_unverified_tls_context_disables_certificate_verification():
    context = _tls_context(verify_tls=False)

    assert context.check_hostname is False
