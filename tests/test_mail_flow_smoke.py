from freemail_api.mail_flow_smoke import (
    LocatedMessage,
    MailFlowResult,
    _dkim_domains_from_header,
    _message,
    _parse_folder,
    _tls_context,
)


def test_mail_flow_result_passed_requires_all_message_flow_steps():
    result = MailFlowResult(
        inbound_accepted=True,
        inbound_found=None,
        submission_accepted=True,
        submission_found=None,
        submission_dkim_domains=[],
        required_dkim_domain="example.com",
        marker="123",
    )

    assert result.passed is False
    assert result.as_dict()["passed"] is False


def test_mail_flow_result_serializes_successful_folder_locations():
    result = MailFlowResult(
        inbound_accepted=True,
        inbound_found=LocatedMessage(folder="Junk Mail", message_ids=["5"]),
        submission_accepted=True,
        submission_found=LocatedMessage(folder="INBOX", message_ids=["6"]),
        submission_dkim_domains=["example.com"],
        required_dkim_domain="example.com",
        marker="123",
    )

    assert result.passed is True
    assert result.as_dict()["inboundFound"] == {"folder": "Junk Mail", "message_ids": ["5"]}
    assert result.as_dict()["submissionDkimDomains"] == ["example.com"]
    assert result.as_dict()["requiredDkimDomain"] == "example.com"


def test_message_builds_basic_rfc822_message():
    message = _message(
        sender="sender@example.net",
        recipient="admin@example.com",
        subject="Smoke",
        body="Body",
    )

    assert message["From"] == "sender@example.net"
    assert message["To"] == "admin@example.com"
    assert message["Subject"] == "Smoke"
    assert message.get_content() == "Body\n"


def test_parse_folder_extracts_quoted_imap_folder_name():
    assert _parse_folder('(\\Junk) "/" "Junk Mail"') == "Junk Mail"


def test_dkim_domains_from_header_extracts_signed_domains():
    header = (
        "DKIM-Signature: v=1; a=rsa-sha256; s=mail; d=example.com; c=relaxed/relaxed;\r\n"
        "DKIM-Signature: v=1; a=rsa-sha256; s=mail; d=example.com; c=relaxed/relaxed;\r\n"
        "Subject: Smoke\r\n"
    )

    assert _dkim_domains_from_header(header) == ["example.com"]


def test_tls_context_can_disable_local_certificate_verification():
    context = _tls_context(verify_tls=False)

    assert context.check_hostname is False
