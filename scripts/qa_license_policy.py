from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from importlib import metadata


ALLOWED_LICENSE_TERMS = {
    "AGPL-3.0-or-later",
    "Apache-2.0",
    "BSD",
    "BSD-3-Clause",
    "ISC",
    "MIT",
    "PostgreSQL",
    "Python",
    "Unlicense",
}
DENIED_LICENSE_TERMS = {
    "Commons Clause",
    "Elastic License",
    "SSPL",
    "BUSL",
    "Business Source License",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate direct runtime dependency licenses and notices.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    failures = scan_license_policy(args.root)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("license policy QA passed")
    return 0


def scan_license_policy(root: Path) -> list[str]:
    root = root.resolve()
    notices = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    failures: list[str] = []
    failures.extend(_check_python_dependencies(root, notices))
    failures.extend(_check_mobile_dependencies(root, notices))
    return failures


def _check_python_dependencies(root: Path, notices: str) -> list[str]:
    failures: list[str] = []
    for package in _runtime_python_packages(root / "requirements.txt"):
        try:
            package_metadata = metadata.metadata(package)
        except metadata.PackageNotFoundError:
            failures.append(f"Python runtime dependency is not installed: {package}")
            continue
        license_text = _python_license_text(package_metadata)
        failures.extend(_check_license(package, license_text))
        failures.extend(_check_notice(package, notices))
    return failures


def _runtime_python_packages(path: Path) -> list[str]:
    packages = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        packages.append(re.split(r"\[|[<>=!~]", stripped, maxsplit=1)[0].strip())
    return packages


def _python_license_text(package_metadata: metadata.PackageMetadata) -> str:
    license_parts = [
        package_metadata.get("License-Expression") or "",
        package_metadata.get("License") or "",
    ]
    license_parts.extend(classifier for classifier in package_metadata.get_all("Classifier") or [] if "License" in classifier)
    return " ".join(license_parts)


def _check_mobile_dependencies(root: Path, notices: str) -> list[str]:
    package_json = json.loads((root / "apps" / "mobile" / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((root / "apps" / "mobile" / "package-lock.json").read_text(encoding="utf-8"))
    packages = package_lock.get("packages", {})
    failures: list[str] = []
    for package in sorted(package_json.get("dependencies", {})):
        metadata_key = f"node_modules/{package}"
        package_metadata = packages.get(metadata_key, {})
        license_text = str(package_metadata.get("license") or "")
        failures.extend(_check_license(package, license_text))
        failures.extend(_check_notice(package, notices))
    return failures


def _check_license(package: str, license_text: str) -> list[str]:
    if not license_text.strip():
        return [f"{package} does not expose license metadata for policy validation"]
    for denied in DENIED_LICENSE_TERMS:
        if denied.lower() in license_text.lower():
            return [f"{package} uses denied license metadata: {license_text}"]
    if any(term.lower() in license_text.lower() for term in ALLOWED_LICENSE_TERMS):
        return []
    return [f"{package} license is not explicitly allowed: {license_text}"]


def _check_notice(package: str, notices: str) -> list[str]:
    if package.lower() in notices.lower():
        return []
    return [f"{package} is missing from THIRD_PARTY_NOTICES.md"]


if __name__ == "__main__":
    sys.exit(main())
