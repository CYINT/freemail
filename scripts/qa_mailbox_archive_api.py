import argparse
import json
from pathlib import Path
import sys
import time
from urllib import error, parse, request
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox archive API with a generated message.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    parser.add_argument("--folder", default="INBOX")
    parser.add_argument("--archive-folder", default="Archive")
    parser.add_argument("--poll-attempts", type=int, default=10)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    subject = f"FreeMail archive API smoke {uuid.uuid4()}"
    try:
        _send_message(args.base_url, args.email, password, args.email, subject)
        message = _wait_for_message(
            args.base_url,
            args.email,
            password,
            args.folder,
            subject,
            attempts=args.poll_attempts,
            interval=args.poll_interval,
        )
        archived = _archive_message(
            args.base_url,
            args.email,
            password,
            folder=str(message["folder"]),
            message_id=str(message["messageId"]),
            archive_folder=args.archive_folder,
        )
        remaining = _find_message(args.base_url, args.email, password, args.folder, subject)
    except (RuntimeError, error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    redacted = {
        "archived": archived.get("archived"),
        "archiveFolder": archived.get("archiveFolder"),
        "sourceFolder": archived.get("folder"),
        "generatedSubject": subject,
        "removedFromSource": remaining is None,
    }
    print(json.dumps(redacted, indent=2, sort_keys=True))
    return 0 if redacted["archived"] and redacted["removedFromSource"] else 1


def _send_message(base_url: str, email: str, password: str, recipient: str, subject: str) -> None:
    payload = {
        "recipients": [recipient],
        "subject": subject,
        "body": "FreeMail generated archive API smoke message.",
    }
    response = _json_request(base_url, "/api/v1/mailbox/send", email, password, method="POST", payload=payload)
    if not response.get("accepted"):
        raise RuntimeError("generated smoke message was not accepted")


def _wait_for_message(
    base_url: str,
    email: str,
    password: str,
    folder: str,
    subject: str,
    *,
    attempts: int,
    interval: float,
) -> dict[str, object]:
    for _attempt in range(max(1, attempts)):
        message = _find_message(base_url, email, password, folder, subject)
        if message:
            return message
        time.sleep(max(0.1, interval))
    raise RuntimeError(f"generated smoke message did not appear in {folder}")


def _find_message(base_url: str, email: str, password: str, folder: str, subject: str) -> dict[str, object] | None:
    query = parse.urlencode({"folder": folder, "limit": "100"})
    snapshot = _json_request(base_url, f"/api/v1/mailbox/snapshot?{query}", email, password)
    for message in snapshot.get("messages", []):
        if isinstance(message, dict) and message.get("subject") == subject:
            return message
    return None


def _archive_message(
    base_url: str,
    email: str,
    password: str,
    *,
    folder: str,
    message_id: str,
    archive_folder: str,
) -> dict[str, object]:
    payload = {"folder": folder, "messageId": message_id, "archiveFolder": archive_folder}
    return _json_request(base_url, "/api/v1/mailbox/message/archive", email, password, method="POST", payload=payload)


def _json_request(
    base_url: str,
    path: str,
    email: str,
    password: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "X-FreeMail-Mailbox-Email": email,
        "X-FreeMail-Mailbox-Password": password,
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    api_request = request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with request.urlopen(api_request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(body) from exc


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
