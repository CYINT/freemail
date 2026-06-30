import argparse
import json
from pathlib import Path
import sys
import time
from urllib import error, parse, request
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox contacts API.")
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
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    subject = f"FreeMail contacts smoke {uuid.uuid4().hex}"
    try:
        _send_message(args.base_url, args.email, password, args.email, subject)
        matched = _wait_for_contact(
            args.base_url,
            args.email,
            password,
            args.folder,
            args.email,
            attempts=args.poll_attempts,
            interval=args.poll_interval,
        )
    except (RuntimeError, error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    redacted = {
        "contactMatched": matched,
        "folder": args.folder,
        "generatedSubject": subject,
    }
    print(json.dumps(redacted, indent=2, sort_keys=True))
    return 0 if matched else 1


def _send_message(base_url: str, email: str, password: str, recipient: str, subject: str) -> None:
    payload = {
        "recipients": [recipient],
        "subject": subject,
        "body": "FreeMail generated contacts smoke message.",
    }
    response = _json_request(base_url, "/api/v1/mailbox/send", email, password, method="POST", payload=payload)
    if not response.get("accepted"):
        raise RuntimeError("generated contacts smoke message was not accepted")


def _wait_for_contact(
    base_url: str,
    email: str,
    password: str,
    folder: str,
    expected_email: str,
    *,
    attempts: int,
    interval: float,
) -> bool:
    for _attempt in range(max(1, attempts)):
        if _contacts_has_email(base_url, email, password, folder, expected_email):
            return True
        time.sleep(max(0.1, interval))
    return False


def _contacts_has_email(base_url: str, email: str, password: str, folder: str, expected_email: str) -> bool:
    params = parse.urlencode({"folder": folder, "limit": "100"})
    result = _json_request(base_url, f"/api/v1/mailbox/contacts?{params}", email, password)
    expected = expected_email.lower()
    return any(
        isinstance(contact, dict) and str(contact.get("email", "")).lower() == expected
        for contact in result["contacts"]
    )


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
