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
        "admin-console",
        "admin-card",
    }
    missing_classes = sorted(required_classes - parser.classes)
    if missing_classes:
        failures.append(f"missing classes: {', '.join(missing_classes)}")

    required_text = ["Inbox", "Compose", "Reply", "Forward", "Attach", "Send", "Junk Mail", "Spam", "Delete"]
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
        "folder-tools",
        "folder-name",
        "folder-create-action",
        "folder-rename-action",
        "folder-delete-action",
        "api-base-url",
        "mailbox-status",
        "message-body",
        "message-attachments",
        "compose-form",
        "compose-attachments",
        "contacts-action",
        "contacts-list",
        "reply-action",
        "forward-action",
        "archive-action",
        "spam-action",
        "delete-action",
        "admin-auth",
        "admin-api-base-url",
        "admin-token",
        "bootstrap-token",
        "admin-status",
        "admin-refresh-action",
        "bootstrap-admin-form",
        "admin-domain-form",
        "admin-user-form",
        "admin-mailbox-form",
        "admin-alias-form",
        "admin-dkim-form",
        "admin-results",
    ]:
        if marker not in " ".join(parser.attributes.get("id", [])):
            failures.append(f"missing live mailbox UI marker: {marker}")
    if "initialPassword" not in html_text(parser):
        failures.append("missing initialPassword admin form field")
    for marker in [
        "fetch(",
        "/api/v1/mailbox/session",
        "/api/v1/mailbox/snapshot",
        "/api/v1/mailbox/search",
        "/api/v1/mailbox/contacts",
        "/api/v1/mailbox/folder",
        "/api/v1/mailbox/message",
        "/api/v1/mailbox/message/attachment",
        "/api/v1/mailbox/message/archive",
        "/api/v1/mailbox/message/move",
        "/api/v1/mailbox/send",
        "/api/v1/bootstrap/admin",
        "/api/v1/admin/domains",
        "/api/v1/admin/users",
        "/api/v1/admin/mailboxes",
        "/api/v1/admin/aliases",
        "/api/v1/admin/dkim-keys",
        "/api/v1/admin/audit-log",
        "/api/v1/admin/domains/${domainId}/dns",
        "/status",
        "archiveMailboxMessage",
        "moveMailboxMessage",
        "searchMailboxMessages",
        "loadMailboxContacts",
        "renderContacts",
        "createMailboxFolder",
        "renameMailboxFolder",
        "deleteMailboxFolder",
        "mutateMailboxFolder",
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
        "restoreAdminSession",
        "persistAdminSession",
        "bootstrapAdministrator",
        "createAdminRecord",
        "loadAdminOverview",
        "renderAdminOverview",
        "adminActionsCell",
        "updateAdminStatus",
        "loadDomainDnsGuidance",
        "domainDnsAction",
        "clearSearch",
    ]:
        if marker not in js_text:
            failures.append(f"missing live mailbox client marker: {marker}")
    if "passwordhash" in html_text(parser).lower() or "passwordHash" in js_text:
        failures.append("web admin client must submit initialPassword, not passwordHash")
    for forbidden in ["sessionStorage", "document.cookie"]:
        if forbidden in js_text:
            failures.append(f"mailbox client must not store credentials with {forbidden}")
    if re.search(r"localStorage\.(setItem|getItem)\([^)]*password", js_text, flags=re.IGNORECASE):
        failures.append("mailbox client must not store mailbox passwords in localStorage")
    if re.search(r"password[^;\n]{0,120}localStorage\.(setItem|getItem)", js_text, flags=re.IGNORECASE):
        failures.append("mailbox client must not store mailbox passwords in localStorage")
    return failures


def html_text(parser: StaticWebParser) -> str:
    return " ".join(parser.text + [item for values in parser.attributes.values() for item in values])


if __name__ == "__main__":
    sys.exit(main())
