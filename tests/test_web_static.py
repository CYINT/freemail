from scripts.qa_web_static import StaticWebParser, _validate


def test_static_web_parser_collects_classes_and_text():
    parser = StaticWebParser()
    parser.feed('<main class="app-shell"><section>Inbox</section></main>')

    assert "app-shell" in parser.classes
    assert "Inbox" in parser.text


def test_static_web_validation_flags_provider_trade_dress_text():
    parser = StaticWebParser()
    parser.feed(
        '<aside class="sidebar"></aside><main class="app-shell workspace">'
        '<nav></nav><header></header><section class="message-list">'
        '<article class="message-row reader compose-panel">Gmail Inbox Compose Reply Forward Attach Send Junk Mail</article>'
        "</section></main>"
    )

    failures = _validate(
        parser,
        "@media (max-width: 640px) {} button { min-height: 38px; outline: 1px solid; border-radius: 8px; }",
        "",
    )

    assert "forbidden provider/trade-dress text found: Gmail" in failures


def test_static_web_validation_flags_credential_storage():
    parser = StaticWebParser()
    parser.feed(
        '<aside class="sidebar"></aside><main class="app-shell workspace">'
        '<script src="./app.js"></script><nav></nav><header></header>'
        '<form class="mailbox-login" id="mailbox-login">'
        '<input id="api-base-url"><p id="mailbox-status">Ready</p></form>'
        '<section class="message-list"><article class="message-row reader compose-panel">'
        "Inbox Compose Reply Forward Attach Send Junk Mail</article></section></main>"
    )

    failures = _validate(
        parser,
        "@media (max-width: 640px) {} button { min-height: 38px; outline: 1px solid; border-radius: 8px; }",
        "fetch('/api/v1/mailbox/snapshot', {headers: {'X-FreeMail-Mailbox-Email': '', "
        "'X-FreeMail-Mailbox-Password': ''}}); localStorage.setItem('mailbox', 'secret');",
    )

    assert "mailbox client must not store credentials with localStorage" in failures
