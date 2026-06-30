import argparse
import json
from pathlib import Path
import sys
import time
from urllib import error, parse, request
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox star-state API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    parser.add_argument("--folder", default="INBOX")
    parser.add_argument("--poll-attempts", type=int, default=10)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
        result = _probe_star_state(
            args.base_url,
            args.email,
            password,
            args.folder,
            attempts=args.poll_attempts,
            interval=args.poll_interval,
        )
    except (RuntimeError, ValueError, error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["starred"] and result["unstarred"] else 1


def _probe_star_state(
    base_url: str,
    email: str,
    password: str,
    folder: str,
    *,
    attempts: int,
    interval: float,
) -> dict[str, object]:
    subject = f"FreeMail star API smoke {uuid.uuid4()}"
    _send_message(base_url, email, password, email, subject)
    message = _wait_for_message(base_url, email, password, folder, subject, attempts=attempts, interval=interval)
    message_id = str(message["messageId"])
    _set_star_state(base_url, email, password, folder, message_id, True)
    starred = _wait_for_star_state(
        base_url,
        email,
        password,
        folder,
        subject,
        True,
        attempts=attempts,
        interval=interval,
    )
    _set_star_state(base_url, email, password, folder, message_id, False)
    unstarred = _wait_for_star_state(
        base_url,
        email,
        password,
        folder,
        subject,
        False,
        attempts=attempts,
        interval=interval,
    )
    return {"folder": folder, "starred": starred, "unstarred": unstarred}


def _send_message(base_url: str, email: str, password: str, recipient: str, subject: str) -> None:
    payload = {
        "recipients": [recipient],
        "subject": subject,
        "body": "FreeMail generated star-state API smoke message.",
    }
    response = _json_request(base_url, "/api/v1/mailbox/send", email, password, method="POST", payload=payload)
    if not response.get("accepted"):
        raise RuntimeError("generated star-state smoke message was not accepted")


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


def _wait_for_star_state(
    base_url: str,
    email: str,
    password: str,
    folder: str,
    subject: str,
    starred: bool,
    *,
    attempts: int,
    interval: float,
) -> bool:
    for _attempt in range(max(1, attempts)):
        message = _find_message(base_url, email, password, folder, subject)
        if message and message.get("starred") is starred:
            return True
        time.sleep(max(0.1, interval))
    return False


def _find_message(base_url: str, email: str, password: str, folder: str, subject: str) -> dict[str, object] | None:
    query = parse.urlencode({"folder": folder, "limit": "100"})
    snapshot = _json_request(base_url, f"/api/v1/mailbox/snapshot?{query}", email, password)
    for message in snapshot.get("messages", []):
        if isinstance(message, dict) and message.get("subject") == subject:
            return message
    return None


def _set_star_state(
    base_url: str,
    email: str,
    password: str,
    folder: str,
    message_id: str,
    starred: bool,
) -> dict[str, object]:
    payload = {"folder": folder, "messageId": message_id, "starred": starred}
    return _json_request(base_url, "/api/v1/mailbox/message/star-state", email, password, method="POST", payload=payload)


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
