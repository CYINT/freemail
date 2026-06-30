import imaplib
import smtplib

from freemail_api.mailbox_smtp import (
    OutboundAttachment,
    SentMessage,
    _append_sent_message,
    _message,
    send_mailbox_message,
)


class FakeSmtp:
    sent_messages = []
    refused = {}

    def __init__(self, host, port, timeout, context):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def ehlo(self, hostname):
        self.ehlo_hostname = hostname

    def login(self, email, password):
        self.login_email = email
        self.login_password = password

    def send_message(self, message):
        self.sent_messages.append(message)
        return self.refused


class FakeImap:
    appended = []
    created = []
    existing_folders = {"Sent Items"}

    def __init__(self, host, port, ssl_context, timeout):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def login(self, email, password):
        self.login_email = email
        self.login_password = password

    def select(self, folder, readonly=False):
        name = folder.strip('"')
        return ("OK", [b"0"]) if name in self.existing_folders else ("NO", [])

    def create(self, folder):
        name = folder.strip('"')
        self.created.append(name)
        self.existing_folders.add(name)
        return "OK", []

    def append(self, folder, flags, date_time, message):
        self.appended.append(
            {
                "folder": folder.strip('"'),
                "flags": flags,
                "dateTime": date_time,
                "message": message,
            }
        )
        return "OK", []


def test_sent_message_serializes():
    sent = SentMessage(
        message_id="<message@example.com>",
        sender="admin@example.com",
        recipients=["hello@example.com"],
        subject="Hello",
    )

    assert sent.as_dict()["message_id"] == "<message@example.com>"


def test_message_builds_submission_headers():
    message = _message(
        sender="admin@example.com",
        recipients=["hello@example.com", "ops@example.com"],
        subject="Hello",
        body="Body",
        message_id="<message@example.com>",
    )

    assert message["From"] == "admin@example.com"
    assert message["To"] == "hello@example.com, ops@example.com"
    assert message["Message-ID"] == "<message@example.com>"
    assert message.get_content().strip() == "Body"


def test_message_builds_attachment_part():
    message = _message(
        sender="admin@example.com",
        recipients=["hello@example.com"],
        subject="Hello",
        body="Body",
        attachments=[OutboundAttachment("report.txt", "text/plain", "cmVwb3J0")],
        message_id="<message@example.com>",
    )

    attachments = [part for part in message.walk() if part.get_content_disposition() == "attachment"]

    assert len(attachments) == 1
    assert attachments[0].get_filename() == "report.txt"
    assert attachments[0].get_payload(decode=True) == b"report"


def test_send_mailbox_message_uses_authenticated_submission(monkeypatch):
    FakeSmtp.sent_messages = []
    FakeSmtp.refused = {}
    monkeypatch.setattr("freemail_api.mailbox_smtp.smtplib.SMTP_SSL", FakeSmtp)

    sent = send_mailbox_message(
        email="admin@example.com",
        password="secret",
        host="127.0.0.1",
        port=2465,
        recipients=[" hello@example.com "],
        subject="Hello",
        body="Body",
    )

    assert sent.sender == "admin@example.com"
    assert sent.recipients == ["hello@example.com"]
    assert sent.subject == "Hello"
    assert sent.sent_folder == "Sent Items"
    assert sent.sent_folder_saved is False
    assert FakeSmtp.sent_messages[0]["Subject"] == "Hello"


def test_send_mailbox_message_appends_accepted_message_to_sent_folder(monkeypatch):
    FakeSmtp.sent_messages = []
    FakeSmtp.refused = {}
    FakeImap.appended = []
    FakeImap.created = []
    FakeImap.existing_folders = {"Sent Items"}
    monkeypatch.setattr("freemail_api.mailbox_smtp.smtplib.SMTP_SSL", FakeSmtp)
    monkeypatch.setattr("freemail_api.mailbox_smtp.imaplib.IMAP4_SSL", FakeImap)

    sent = send_mailbox_message(
        email="admin@example.com",
        password="secret",
        host="127.0.0.1",
        port=2465,
        imap_host="127.0.0.1",
        imap_port=2993,
        recipients=["hello@example.com"],
        subject="Hello",
        body="Body",
    )

    assert sent.sent_folder == "Sent Items"
    assert sent.sent_folder_saved is True
    assert FakeImap.appended[0]["folder"] == "Sent Items"
    assert FakeImap.appended[0]["flags"] == r"(\Seen)"
    assert FakeImap.appended[0]["dateTime"] is None
    assert b"Subject: Hello" in FakeImap.appended[0]["message"]


def test_append_sent_message_creates_missing_sent_folder(monkeypatch):
    FakeImap.appended = []
    FakeImap.created = []
    FakeImap.existing_folders = set()
    monkeypatch.setattr("freemail_api.mailbox_smtp.imaplib.IMAP4_SSL", FakeImap)

    saved = _append_sent_message(
        email="admin@example.com",
        password="secret",
        host="127.0.0.1",
        port=2993,
        folder="Sent Items",
        message=_message(
            sender="admin@example.com",
            recipients=["hello@example.com"],
            subject="Hello",
            body="Body",
            message_id="<message@example.com>",
        ),
        timeout_seconds=10,
        verify_tls=False,
    )

    assert saved is True
    assert FakeImap.created == ["Sent Items"]
    assert FakeImap.appended[0]["folder"] == "Sent Items"


def test_append_sent_message_reports_failure_without_raising(monkeypatch):
    class FailingImap(FakeImap):
        def login(self, email, password):
            raise imaplib.IMAP4.error("login failed")

    monkeypatch.setattr("freemail_api.mailbox_smtp.imaplib.IMAP4_SSL", FailingImap)

    saved = _append_sent_message(
        email="admin@example.com",
        password="secret",
        host="127.0.0.1",
        port=2993,
        folder="Sent Items",
        message=_message(
            sender="admin@example.com",
            recipients=["hello@example.com"],
            subject="Hello",
            body="Body",
            message_id="<message@example.com>",
        ),
        timeout_seconds=10,
        verify_tls=False,
    )

    assert saved is False


def test_send_mailbox_message_raises_refused_recipients(monkeypatch):
    FakeSmtp.sent_messages = []
    FakeSmtp.refused = {"bad@example.com": (550, b"refused")}
    monkeypatch.setattr("freemail_api.mailbox_smtp.smtplib.SMTP_SSL", FakeSmtp)

    try:
        send_mailbox_message(
            email="admin@example.com",
            password="secret",
            host="127.0.0.1",
            port=2465,
            recipients=["bad@example.com"],
            subject="Hello",
            body="Body",
        )
    except smtplib.SMTPRecipientsRefused as error:
        assert "bad@example.com" in error.recipients
    else:
        raise AssertionError("Expected SMTPRecipientsRefused")
