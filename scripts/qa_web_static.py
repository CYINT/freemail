from html.parser import HTMLParser
from pathlib import Path
import re
import sys


class StaticWebParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.classes: set[str] = set()
        self.text: list[str] = []
        self.attributes: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        for name, value in attrs:
            if value is None:
                continue
            self.attributes.setdefault(name, []).append(value)
            if name == "class":
                self.classes.update(value.split())

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.text.append(value)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    html = root / "apps" / "web" / "index.html"
    css = root / "apps" / "web" / "styles.css"
    js = root / "apps" / "web" / "app.js"
    parser = StaticWebParser()
    parser.feed(html.read_text(encoding="utf-8"))
    css_text = css.read_text(encoding="utf-8")
    js_text = js.read_text(encoding="utf-8")

    failures = _validate(parser, css_text, js_text)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("static web QA passed")
    return 0


def _validate(parser: StaticWebParser, css_text: str, js_text: str) -> list[str]:
    failures = []
    required_classes = {
        "app-shell",
        "sidebar",
        "workspace",
        "message-list",
        "message-row",
        "reader",
        "compose-panel",
        "mailbox-login",
    }
    missing_classes = sorted(required_classes - parser.classes)
    if missing_classes:
        failures.append(f"missing classes: {', '.join(missing_classes)}")

    required_text = ["Inbox", "Compose", "Reply", "Forward", "Attach", "Send", "Junk Mail"]
    page_text = " ".join(parser.text)
    for text in required_text:
        if text not in page_text:
            failures.append(f"missing text: {text}")

    forbidden_text = ["Gmail", "Google", "Trello"]
    for text in forbidden_text:
        if text.lower() in page_text.lower():
            failures.append(f"forbidden provider/trade-dress text found: {text}")

    for tag in ["aside", "main", "nav", "header", "section", "article"]:
        if tag not in parser.tags:
            failures.append(f"missing semantic tag: {tag}")

    if "@media" not in css_text:
        failures.append("missing responsive media queries")
    if "min-height: 38px" not in css_text:
        failures.append("missing minimum button target sizing")
    if "outline:" not in css_text:
        failures.append("missing visible focus styling")
    if "border-radius: 8px" not in css_text:
        failures.append("missing bounded 8px radius")
    if "./app.js" not in parser.attributes.get("src", []):
        failures.append("missing webmail client script")
    for marker in [
        "mailbox-login",
        "mailbox-logout",
        "mailbox-search",
        "search-query",
        "api-base-url",
        "mailbox-status",
        "message-body",
        "message-attachments",
        "compose-form",
        "compose-attachments",
        "reply-action",
        "forward-action",
        "archive-action",
    ]:
        if marker not in " ".join(parser.attributes.get("id", [])):
            failures.append(f"missing live mailbox UI marker: {marker}")
    for marker in [
        "fetch(",
        "/api/v1/mailbox/session",
        "/api/v1/mailbox/snapshot",
        "/api/v1/mailbox/search",
        "/api/v1/mailbox/message",
        "/api/v1/mailbox/message/attachment",
        "/api/v1/mailbox/message/archive",
        "/api/v1/mailbox/send",
        "archiveMailboxMessage",
        "searchMailboxMessages",
        "downloadMailboxAttachment",
        "filesToAttachments",
        "fileToBase64",
        "renderMessageBody",
        "renderMessageAttachments",
        "prefillReply",
        "prefillForward",
        "quoteMessage",
        'method: "POST"',
        '"Content-Type": "application/json"',
        "Authorization",
        "Bearer",
        "restoreMailboxSession",
        "persistMailboxSession",
        "forgetMailboxSession",
        "clearSearch",
    ]:
        if marker not in js_text:
            failures.append(f"missing live mailbox client marker: {marker}")
    for forbidden in ["sessionStorage", "document.cookie"]:
        if forbidden in js_text:
            failures.append(f"mailbox client must not store credentials with {forbidden}")
    if re.search(r"localStorage\.(setItem|getItem)\([^)]*password", js_text, flags=re.IGNORECASE):
        failures.append("mailbox client must not store mailbox passwords in localStorage")
    if re.search(r"password[^;\n]{0,120}localStorage\.(setItem|getItem)", js_text, flags=re.IGNORECASE):
        failures.append("mailbox client must not store mailbox passwords in localStorage")
    return failures


if __name__ == "__main__":
    sys.exit(main())
