import argparse
import json
from pathlib import Path
import sys
from urllib import error, request


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox draft-save API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    parser.add_argument("--recipient", default="")
    parser.add_argument("--subject", default="FreeMail API draft smoke")
    parser.add_argument("--body", default="FreeMail mailbox draft API smoke.")
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    recipients = [args.recipient] if args.recipient else []
    payload = json.dumps(
        {
            "recipients": recipients,
            "subject": args.subject,
            "body": args.body,
            "draftFolder": "Drafts",
        }
    ).encode("utf-8")
    api_request = request.Request(
        f"{args.base_url.rstrip('/')}/api/v1/mailbox/draft",
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
        "saved": data.get("saved"),
        "sender": data.get("sender"),
        "recipientCount": len(data.get("recipients", [])),
        "subject": data.get("subject"),
        "draftFolder": data.get("draftFolder"),
        "hasMessageId": bool(data.get("messageId")),
    }
    print(json.dumps(redacted, indent=2, sort_keys=True))
    return 0 if redacted["saved"] and redacted["hasMessageId"] and redacted["draftFolder"] == "Drafts" else 1


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
