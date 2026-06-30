from email.message import EmailMessage

from freemail_api.mailbox_imap import (
    ArchivedMailboxMessage,
    BulkActionMailboxMessages,
    MailboxAttachment,
    MailboxContact,
    MailboxContacts,
    MailboxFolder,
    MailboxMessage,
    MailboxMessageDetail,
    MailboxMessagePage,
    MailboxSearchResult,
    MovedMailboxMessage,
    MailboxSnapshot,
    MutatedMailboxFolder,
    ReadStateMailboxMessage,
    StarStateMailboxMessage,
    _archive_message,
    _attachment_contents_from_message,
    _attachments_from_message,
    _body_from_message,
    _bulk_flag_command,
    _bulk_move_messages,
    _bulk_store_flags,
    _bulk_target_folder,
    _contacts_from_header,
    _count_from_select,
    _create_folder,
    _delete_folder,
    _ensure_folder,
    _flags_from_fetch,
    _get_attachment,
    _get_message,
    _list_contacts,
    _list_folders,
    _list_messages,
    _message_ids_for_move,
    _move_message,
    _parse_folder,
    _quote_search_value,
    _rename_folder,
    _search_criteria,
    _search_messages,
    _set_message_flagged,
    _set_message_seen,
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
        self.renamed_folders = []
        self.deleted_folders = []

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
        prefix = b"3 (FLAGS (\\Seen \\Flagged) BODY[HEADER] {%d}" % len(payload)
        return "OK", [(prefix, payload)]

    def create(self, folder):
        self.created_folders.append(folder)
        return "OK", []

    def rename(self, folder, target_folder):
        self.renamed_folders.append((folder, target_folder))
        return "OK", []

    def delete(self, folder):
        self.deleted_folders.append(folder)
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
                starred=True,
            )
        ],
        limit=25,
        offset=0,
        next_offset=None,
        has_more=False,
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
                "starred": True,
            }
        ],
        "limit": 25,
        "offset": 0,
        "next_offset": None,
        "has_more": False,
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
        starred=True,
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
                starred=True,
            )
        ],
        limit=25,
        offset=0,
        next_offset=None,
        has_more=False,
    )

    assert result.as_dict()["query"] == "hello"
    assert result.as_dict()["messages"][0]["subject"] == "Hello"
    assert result.as_dict()["has_more"] is False


def test_contacts_serializes_records():
    contacts = MailboxContacts(
        email="admin@example.com",
        folder="INBOX",
        contacts=[MailboxContact(name="Sender", email="sender@example.com", message_count=2)],
    )

    assert contacts.as_dict() == {
        "email": "admin@example.com",
        "folder": "INBOX",
        "contacts": [{"name": "Sender", "email": "sender@example.com", "message_count": 2}],
    }


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


def test_read_state_message_serializes_flag_result():
    state = ReadStateMailboxMessage(folder="INBOX", message_id="7", read=True, unread=False)

    assert state.as_dict() == {
        "folder": "INBOX",
        "message_id": "7",
        "read": True,
        "unread": False,
    }


def test_star_state_message_serializes_flag_result():
    state = StarStateMailboxMessage(folder="INBOX", message_id="7", starred=True)

    assert state.as_dict() == {
        "folder": "INBOX",
        "message_id": "7",
        "starred": True,
    }


def test_bulk_action_message_serializes_bulk_result():
    result = BulkActionMailboxMessages(
        folder="INBOX",
        action="archive",
        message_ids=["1", "2"],
        target_folder="Archive",
        succeeded=2,
    )

    assert result.as_dict() == {
        "folder": "INBOX",
        "action": "archive",
        "message_ids": ["1", "2"],
        "target_folder": "Archive",
        "succeeded": 2,
    }


def test_mutated_folder_serializes_folder_action():
    mutation = MutatedMailboxFolder(folder="Clients", target_folder="Customers", action="rename", success=True)

    assert mutation.as_dict() == {
        "folder": "Clients",
        "target_folder": "Customers",
        "action": "rename",
        "success": True,
    }


def test_list_folders_counts_messages_and_unread():
    folders = _list_folders(FakeImap())

    assert [folder.name for folder in folders] == ["INBOX", "Sent Items"]
    assert folders[0].message_count == 3
    assert folders[0].unread_count == 2


def test_list_messages_parses_headers_and_seen_flag():
    page = _list_messages(FakeImap(), folder="INBOX", limit=1)
    messages = page.messages

    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].sender == "sender@example.com"
    assert messages[0].recipients == "admin@example.com"
    assert messages[0].unread is False
    assert messages[0].starred is True
    assert page.next_offset == 1
    assert page.has_more is True


def test_list_messages_paginates_newest_first_with_offset():
    page = _list_messages(FakeImap(), folder="INBOX", limit=1, offset=1)

    assert page.messages[0].message_id == "2"
    assert page.next_offset == 2
    assert page.has_more is True


def test_message_page_serializes_pagination_state():
    page = MailboxMessagePage(messages=[], next_offset=50, has_more=True)

    assert page.next_offset == 50
    assert page.has_more is True


def test_search_messages_uses_sender_recipient_subject_and_body_criteria():
    imap = FakeImap()

    page = _search_messages(imap, folder="INBOX", query="hello", limit=2)
    messages = page.messages

    assert len(messages) == 2
    assert messages[0].subject == "Hello"
    assert page.next_offset == 2
    assert imap.search_calls[-1] == (None, _search_criteria("hello"))


def test_search_messages_returns_empty_for_blank_query():
    assert _search_messages(FakeImap(), folder="INBOX", query=" ", limit=10) == MailboxMessagePage(
        messages=[],
        next_offset=None,
        has_more=False,
    )


def test_list_contacts_deduplicates_addresses_by_frequency():
    contacts = _list_contacts(FakeImap(), folder="INBOX", limit=3)

    assert contacts == [
        MailboxContact(name="", email="admin@example.com", message_count=3),
        MailboxContact(name="", email="sender@example.com", message_count=3),
    ]


def test_contacts_from_header_parses_common_address_fields():
    message = EmailMessage()
    message["From"] = "Sender <sender@example.com>"
    message["Reply-To"] = "Replies <reply@example.com>"
    message["To"] = "Admin <admin@example.com>"
    message["Cc"] = "Copy <copy@example.com>"

    assert _contacts_from_header(message) == [
        ("Sender", "sender@example.com"),
        ("Replies", "reply@example.com"),
        ("Admin", "admin@example.com"),
        ("Copy", "copy@example.com"),
    ]


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
    assert message.starred is True
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


def test_set_message_seen_adds_seen_flag_for_read_state():
    imap = FakeImap()

    _set_message_seen(imap, folder="INBOX", message_id="5", read=True)

    assert imap.selected_folders == [('"INBOX"', False)]
    assert imap.stored_flags == [(b"5", "+FLAGS", r"(\Seen)")]


def test_set_message_seen_removes_seen_flag_for_unread_state():
    imap = FakeImap()

    _set_message_seen(imap, folder="INBOX", message_id="5", read=False)

    assert imap.selected_folders == [('"INBOX"', False)]
    assert imap.stored_flags == [(b"5", "-FLAGS", r"(\Seen)")]


def test_set_message_flagged_adds_flagged_flag_for_star_state():
    imap = FakeImap()

    _set_message_flagged(imap, folder="INBOX", message_id="6", starred=True)

    assert imap.selected_folders == [('"INBOX"', False)]
    assert imap.stored_flags == [(b"6", "+FLAGS", r"(\Flagged)")]


def test_set_message_flagged_removes_flagged_flag_for_unstar_state():
    imap = FakeImap()

    _set_message_flagged(imap, folder="INBOX", message_id="6", starred=False)

    assert imap.selected_folders == [('"INBOX"', False)]
    assert imap.stored_flags == [(b"6", "-FLAGS", r"(\Flagged)")]


def test_bulk_store_flags_updates_each_message_with_one_select():
    imap = FakeImap()

    succeeded = _bulk_store_flags(imap, folder="INBOX", message_ids=["1", "2"], action="star")

    assert succeeded == 2
    assert imap.selected_folders == [('"INBOX"', False)]
    assert imap.stored_flags == [(b"1", "+FLAGS", r"(\Flagged)"), (b"2", "+FLAGS", r"(\Flagged)")]


def test_bulk_move_messages_processes_sequence_ids_descending_then_expunges_once():
    imap = FakeImap()

    succeeded = _bulk_move_messages(imap, folder="INBOX", message_ids=["1", "3", "2"], target_folder="Archive")

    assert succeeded == 3
    assert imap.selected_folders == [('"INBOX"', False), ('"Archive"', True), ('"INBOX"', False)]
    assert imap.copied_messages == [(b"3", '"Archive"'), (b"2", '"Archive"'), (b"1", '"Archive"')]
    assert imap.stored_flags == [
        (b"3", "+FLAGS", r"(\Deleted)"),
        (b"2", "+FLAGS", r"(\Deleted)"),
        (b"1", "+FLAGS", r"(\Deleted)"),
    ]
    assert imap.expunge_called is True


def test_bulk_helpers_resolve_flags_targets_and_move_order():
    assert _bulk_flag_command("read") == ("+FLAGS", r"(\Seen)")
    assert _bulk_flag_command("unread") == ("-FLAGS", r"(\Seen)")
    assert _bulk_flag_command("unstar") == ("-FLAGS", r"(\Flagged)")
    assert _bulk_target_folder("archive", None) == "Archive"
    assert _bulk_target_folder("spam", None) == "Junk Mail"
    assert _bulk_target_folder("delete", None) == "Deleted Items"
    assert _bulk_target_folder("move", "Clients") == "Clients"
    assert _message_ids_for_move(["10", "2", "1"]) == ["10", "2", "1"]
    assert _message_ids_for_move(["abc", "2", "1"]) == ["1", "2", "abc"]


def test_ensure_folder_creates_missing_archive_folder():
    class MissingFolderImap(FakeImap):
        def select(self, folder, readonly=True):
            self.selected_folder = folder
            return ("NO", []) if folder == '"Archive"' else ("OK", [b"1"])

    imap = MissingFolderImap()

    _ensure_folder(imap, "Archive")

    assert imap.created_folders == ['"Archive"']


def test_create_folder_calls_imap_create():
    imap = FakeImap()

    _create_folder(imap, "Clients")

    assert imap.created_folders == ['"Clients"']


def test_rename_folder_calls_imap_rename():
    imap = FakeImap()

    _rename_folder(imap, folder="Clients", target_folder="Customers")

    assert imap.renamed_folders == [('"Clients"', '"Customers"')]


def test_delete_folder_calls_imap_delete():
    imap = FakeImap()

    _delete_folder(imap, "Customers")

    assert imap.deleted_folders == ['"Customers"']


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
    _create_folder,
    _delete_folder,
