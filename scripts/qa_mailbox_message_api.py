import argparse
import json
from pathlib import Path
import sys
from urllib import error, parse, request


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox message detail API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    parser.add_argument("--folder", default="INBOX")
    parser.add_argument("--message-id")
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
        message_id = args.message_id or _first_message_id(args.base_url, args.email, password, args.folder)
        data = _request_message(args.base_url, args.email, password, args.folder, message_id)
    except (ValueError, error.HTTPError) as exc:
        detail = exc.read().decode("utf-8", errors="replace") if isinstance(exc, error.HTTPError) else str(exc)
        print(detail, file=sys.stderr)
        return 1

    redacted = {
        "folder": data.get("folder"),
        "messageId": data.get("messageId"),
        "subject": data.get("subject"),
        "sender": data.get("sender"),
        "bodyLength": len(data.get("body", "")),
    }
    print(json.dumps(redacted, indent=2, sort_keys=True))
    return 0 if redacted["messageId"] and redacted["bodyLength"] >= 0 else 1


def _first_message_id(base_url: str, email: str, password: str, folder: str) -> str:
    query = parse.urlencode({"folder": folder, "limit": 1})
    api_request = request.Request(
        f"{base_url.rstrip('/')}/api/v1/mailbox/snapshot?{query}",
        headers={
            "X-FreeMail-Mailbox-Email": email,
            "X-FreeMail-Mailbox-Password": password,
        },
    )
    with request.urlopen(api_request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    messages = data.get("messages", [])
    if not messages:
        raise ValueError(f"No messages in {folder}")
    return str(messages[0]["messageId"])


def _request_message(base_url: str, email: str, password: str, folder: str, message_id: str) -> dict[str, object]:
    query = parse.urlencode({"folder": folder, "message_id": message_id})
    api_request = request.Request(
        f"{base_url.rstrip('/')}/api/v1/mailbox/message?{query}",
        headers={
            "X-FreeMail-Mailbox-Email": email,
            "X-FreeMail-Mailbox-Password": password,
        },
    )
    with request.urlopen(api_request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("message API response must be an object")
    return data


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
