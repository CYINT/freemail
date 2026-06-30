import argparse
import json
from pathlib import Path
import sys
from urllib import error, parse, request


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail read-only mailbox snapshot API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    parser.add_argument("--folder", default="INBOX")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    query = parse.urlencode({"folder": args.folder, "limit": args.limit, "offset": args.offset})
    url = f"{args.base_url.rstrip('/')}/api/v1/mailbox/snapshot?{query}"
    api_request = request.Request(
        url,
        headers={
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
        "email": data.get("email"),
        "folderCount": len(data.get("folders", [])),
        "messageCount": len(data.get("messages", [])),
        "limit": data.get("limit"),
        "offset": data.get("offset"),
        "nextOffset": data.get("nextOffset"),
        "hasMore": data.get("hasMore"),
        "folders": [folder.get("name") for folder in data.get("folders", [])],
    }
    print(json.dumps(redacted, indent=2, sort_keys=True))
    return 0 if redacted["folderCount"] else 1


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
