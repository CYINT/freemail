from __future__ import annotations

import argparse
from fnmatch import fnmatch
from pathlib import Path
import re
import subprocess
import sys


FORBIDDEN_FILE_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.crt",
    "*.p12",
    "*.pfx",
    "*.mobileprovision",
    "*.keystore",
    "*.jks",
    "*service-account*.json",
    "*credentials*.json",
    "*secrets*.json",
)
ALLOWED_TRACKED_FILES = {
    ".env.example",
}
ALLOWED_SECRET_CONTENT_PATHS = (
    "tests/*",
    "docs/*",
)
SECRET_PATTERNS = {
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh[opsu]_[A-Za-z0-9_]{36,}\b"),
    "google-api-key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "slack-token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan tracked FreeMail files for committed secrets and signing material.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    failures = scan_repo(args.root)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("repo secret QA passed")
    return 0


def scan_repo(root: Path) -> list[str]:
    root = root.resolve()
    files = _tracked_files(root)
    failures: list[str] = []
    for relative_path in files:
        normalized = relative_path.as_posix()
        failures.extend(_check_filename(normalized))
        failures.extend(_check_content(root / relative_path, normalized))
    return failures


def _tracked_files(root: Path) -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=False,
    ).stdout
    return [Path(item.decode("utf-8")) for item in output.split(b"\0") if item]


def _check_filename(path: str) -> list[str]:
    if path in ALLOWED_TRACKED_FILES:
        return []
    name = Path(path).name
    for pattern in FORBIDDEN_FILE_PATTERNS:
        if fnmatch(name, pattern) or fnmatch(path, pattern):
            return [f"forbidden tracked secret/signing file: {path}"]
    return []


def _check_content(path: Path, normalized_path: str) -> list[str]:
    if _content_allowlisted(normalized_path):
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    failures = []
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(content):
            failures.append(f"possible committed secret ({label}) in {normalized_path}")
    return failures


def _content_allowlisted(path: str) -> bool:
    return any(fnmatch(path, pattern) for pattern in ALLOWED_SECRET_CONTENT_PATHS)


if __name__ == "__main__":
    sys.exit(main())
