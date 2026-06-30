import argparse
import json
from pathlib import Path
import sys
from urllib import error, parse, request
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the FreeMail mailbox folder management API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18090")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    parser.add_argument("--secrets-json")
    args = parser.parse_args()

    try:
        password = args.password or _load_password(args.secrets_json, args.email)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    token = uuid.uuid4().hex[:12]
    folder = f"QA Folder {token}"
    renamed_folder = f"QA Renamed {token}"
    try:
        created = _mutate_folder(args.base_url, args.email, password, "POST", {"folder": folder})
        renamed = _mutate_folder(
            args.base_url,
            args.email,
            password,
            "PATCH",
            {"folder": folder, "targetFolder": renamed_folder},
        )
        renamed_visible = _snapshot_has_folder(args.base_url, args.email, password, renamed_folder)
        emptied = _empty_folder(args.base_url, args.email, password, renamed_folder)
        deleted = _mutate_folder(args.base_url, args.email, password, "DELETE", {"folder": renamed_folder})
        deleted_absent = not _snapshot_has_folder(args.base_url, args.email, password, renamed_folder)
    except (RuntimeError, error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    redacted = {
        "created": bool(created.get("success")),
        "emptied": bool(emptied.get("success")),
        "emptyDeletedCount": emptied.get("deletedCount"),
        "deleted": bool(deleted.get("success")),
        "deletedAbsent": deleted_absent,
        "renamed": bool(renamed.get("success")),
        "renamedVisible": renamed_visible,
    }
    print(json.dumps(redacted, indent=2, sort_keys=True))
    checks = [redacted["created"], redacted["emptied"], redacted["emptyDeletedCount"] == 0, redacted["deleted"], redacted["deletedAbsent"], redacted["renamed"], redacted["renamedVisible"]]
    return 0 if all(checks) else 1


def _snapshot_has_folder(base_url: str, email: str, password: str, folder: str) -> bool:
    params = parse.urlencode({"folder": "INBOX", "limit": "1"})
    result = _json_request(base_url, f"/api/v1/mailbox/snapshot?{params}", email, password)
    return any(isinstance(row, dict) and row.get("name") == folder for row in result.get("folders", []))


def _mutate_folder(
    base_url: str,
    email: str,
    password: str,
    method: str,
    payload: dict[str, object],
) -> dict[str, object]:
    return _json_request(base_url, "/api/v1/mailbox/folder", email, password, method=method, payload=payload)


def _empty_folder(base_url: str, email: str, password: str, folder: str) -> dict[str, object]:
    return _json_request(
        base_url,
        "/api/v1/mailbox/folder/empty",
        email,
        password,
        method="POST",
        payload={"folder": folder},
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
