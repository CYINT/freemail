import argparse
import base64
from email.message import EmailMessage
from email.utils import make_msgid
import json
from pathlib import Path
import sys
from urllib import error, parse, request


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox EML import API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    parser.add_argument("--folder", default="INBOX")
    parser.add_argument("--subject", default="FreeMail EML import smoke")
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
        content = _message_source(sender=args.email, recipient=args.email, subject=args.subject)
        imported = _import_message(args.base_url, args.email, password, args.folder, content)
        found = _search_subject(args.base_url, args.email, password, args.folder, args.subject)
    except (ValueError, error.HTTPError) as exc:
        detail = exc.read().decode("utf-8", errors="replace") if isinstance(exc, error.HTTPError) else str(exc)
        print(detail, file=sys.stderr)
        return 1

    redacted = {
        "folder": imported.get("folder"),
        "filename": imported.get("filename"),
        "imported": imported.get("imported"),
        "sourceBytes": imported.get("size"),
        "foundBySubject": found,
    }
    print(json.dumps(redacted, indent=2, sort_keys=True))
    return 0 if redacted["imported"] and redacted["sourceBytes"] and found else 1


def _message_source(*, sender: str, recipient: str, subject: str) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain="freemail.local")
    message.set_content("FreeMail mailbox EML import API smoke.")
    return message.as_bytes()


def _import_message(base_url: str, email: str, password: str, folder: str, content: bytes) -> dict[str, object]:
    payload = json.dumps(
        {
            "folder": folder,
            "filename": "freemail-import-smoke.eml",
            "contentBase64": base64.b64encode(content).decode("ascii"),
        }
    ).encode("utf-8")
    api_request = request.Request(
        f"{base_url.rstrip('/')}/api/v1/mailbox/message/import",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-FreeMail-Mailbox-Email": email,
            "X-FreeMail-Mailbox-Password": password,
        },
    )
    with request.urlopen(api_request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("import API response must be an object")
    return data


def _search_subject(base_url: str, email: str, password: str, folder: str, subject: str) -> bool:
    query = parse.urlencode({"folder": folder, "query": subject, "limit": 10})
    api_request = request.Request(
        f"{base_url.rstrip('/')}/api/v1/mailbox/search?{query}",
        headers={
            "X-FreeMail-Mailbox-Email": email,
            "X-FreeMail-Mailbox-Password": password,
        },
    )
    with request.urlopen(api_request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    return any(message.get("subject") == subject for message in data.get("messages", []))


def _load_password(path: str | None, email: str) -> str:
    if not path:
        raise ValueError("Provide --password or --secrets-json")
    with Path(path).open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("secrets JSON must be an object mapping email addresses to passwords")
    try:
        return str(data[email.lower()])
    except KeyError as error:
        raise ValueError(f"Missing password for {email}") from error


if __name__ == "__main__":
    sys.exit(main())
