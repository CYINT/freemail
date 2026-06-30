import argparse
import json
from pathlib import Path
import sys
from urllib import error, request


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox send API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--subject", default="FreeMail API send smoke")
    parser.add_argument("--body", default="FreeMail mailbox send API smoke.")
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    payload = json.dumps(
        {
            "recipients": [args.recipient],
            "subject": args.subject,
            "body": args.body,
        }
    ).encode("utf-8")
    api_request = request.Request(
        f"{args.base_url.rstrip('/')}/api/v1/mailbox/send",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-FreeMail-Mailbox-Email": args.email,
            "X-FreeMail-Mailbox-Password": password,
        },
    )
    try:
        with request.urlopen(api_request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1

    redacted = {
        "accepted": data.get("accepted"),
        "sender": data.get("sender"),
        "recipientCount": len(data.get("recipients", [])),
        "subject": data.get("subject"),
        "hasMessageId": bool(data.get("messageId")),
        "sentFolder": data.get("sentFolder"),
        "sentFolderSaved": data.get("sentFolderSaved"),
    }
    print(json.dumps(redacted, indent=2, sort_keys=True))
    return 0 if redacted["accepted"] and redacted["hasMessageId"] and redacted["sentFolderSaved"] else 1


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
