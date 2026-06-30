from freemail_api.mailbox_imap import (
    MailboxFolder,
    MailboxMessage,
    MailboxSnapshot,
    _count_from_select,
    _flags_from_fetch,
    _list_folders,
    _list_messages,
    _parse_folder,
    _tls_context,
)


class FakeImap:
    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent Items"']

    def select(self, folder, readonly=True):
        self.selected_folder = folder
        return "OK", [b"3"]

    def search(self, charset, criteria):
        if criteria == "UNSEEN":
            return "OK", [b"1 3"]
        return "OK", [b"1 2 3"]

    def fetch(self, message_id, query):
        headers = (
            b"Subject: Hello\r\n"
            b"From: sender@example.com\r\n"
            b"To: admin@example.com\r\n"
            b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
            b"\r\n"
        )
        prefix = b"3 (FLAGS (\\Seen) BODY[HEADER] {%d}" % len(headers)
        return "OK", [(prefix, headers)]


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
