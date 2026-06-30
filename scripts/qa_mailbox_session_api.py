import argparse
import json
from pathlib import Path
import sys
from urllib import error, parse, request


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox session API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    parser.add_argument("--folder", default="INBOX")
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
        session = _create_session(args.base_url, args.email, password)
        snapshot = _snapshot(args.base_url, str(session["token"]), args.folder)
        _delete_session(args.base_url, str(session["token"]))
        revoked = _snapshot_rejected(args.base_url, str(session["token"]), args.folder)
    except (RuntimeError, ValueError, error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    redacted = {
        "email": session.get("email"),
        "expiresAt": session.get("expiresAt"),
        "folders": len(snapshot.get("folders", [])),
        "messages": len(snapshot.get("messages", [])),
        "revokedTokenRejected": revoked,
    }
    print(json.dumps(redacted, indent=2, sort_keys=True))
    return 0 if revoked else 1


def _create_session(base_url: str, email: str, password: str) -> dict[str, object]:
    payload = {"email": email, "password": password}
    return _json_request(base_url, "/api/v1/mailbox/session", method="POST", payload=payload)


def _snapshot(base_url: str, token: str, folder: str) -> dict[str, object]:
    query = parse.urlencode({"folder": folder, "limit": "25"})
    return _json_request(base_url, f"/api/v1/mailbox/snapshot?{query}", token=token)


def _delete_session(base_url: str, token: str) -> None:
    _json_request(base_url, "/api/v1/mailbox/session", method="DELETE", token=token)


def _snapshot_rejected(base_url: str, token: str, folder: str) -> bool:
    try:
        _snapshot(base_url, token, folder)
    except RuntimeError as exc:
        return "401" in str(exc) or "Invalid mailbox session" in str(exc)
    return False


def _json_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    token: str | None = None,
) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    api_request = request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with request.urlopen(api_request, timeout=15) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code}: {body}") from exc


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
