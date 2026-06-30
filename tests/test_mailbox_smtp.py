import smtplib

from freemail_api.mailbox_smtp import SentMessage, _message, send_mailbox_message


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
    assert FakeSmtp.sent_messages[0]["Subject"] == "Hello"


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
