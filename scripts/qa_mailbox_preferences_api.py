import argparse
import json
from pathlib import Path
import sys
from urllib import error, request
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox preferences API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
        result = _probe_preferences(args.base_url, args.email, password)
    except (RuntimeError, ValueError, error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["updated"] and result["restored"] else 1


def _probe_preferences(base_url: str, email: str, password: str) -> dict[str, object]:
    previous = _json_request(base_url, "/api/v1/mailbox/preferences", email, password)
    marker = f"FreeMail preferences smoke {uuid.uuid4()}"
    updated = _json_request(
        base_url,
        "/api/v1/mailbox/preferences",
        email,
        password,
        method="PUT",
        payload={"displayName": "FreeMail QA", "signature": marker},
    )
    loaded = _json_request(base_url, "/api/v1/mailbox/preferences", email, password)
    restored = _json_request(
        base_url,
        "/api/v1/mailbox/preferences",
        email,
        password,
        method="PUT",
        payload={
            "displayName": str(previous.get("displayName") or ""),
            "signature": str(previous.get("signature") or ""),
        },
    )
    return {
        "mailboxEmail": loaded.get("mailboxEmail"),
        "updated": updated.get("signature") == marker and loaded.get("signature") == marker,
        "restored": restored.get("signature") == previous.get("signature", ""),
        "previousSignatureLength": len(str(previous.get("signature") or "")),
        "updatedSignatureLength": len(marker),
    }


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
    api_request = request.Request(f"{base_url.rstrip('/')}{path}", data=data, method=method, headers=headers)
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
