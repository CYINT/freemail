from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from scripts.qa_license_policy import scan_license_policy
from scripts.qa_repo_secrets import scan_repo


REQUIRED_FILES = {
    "LICENSE": ("GNU AFFERO GENERAL PUBLIC LICENSE", "Version 3"),
    "README.md": ("AGPL-3.0-or-later", "FreeMail", "not affiliated", "VPN-only"),
    "CONTRIBUTING.md": ("contribut",),
    "CODE_OF_CONDUCT.md": ("code of conduct",),
    "SECURITY.md": ("security",),
    "THIRD_PARTY_NOTICES.md": ("Third-Party",),
    ".env.example": ("FREEMAIL_",),
    "docs/deployment-vpn.md": ("VPN", "freemail.kuzuryu.ai"),
    "docs/release-gates.md": ("release gate", "private-beta"),
    "docs/mobile-release.md": ("signing", "store"),
}
REQUIRED_CI_STEPS = (
    "Repository secret scan",
    "License policy scan",
    "Tests",
    "Browser webmail QA",
    "Mobile static QA",
    "Mobile native prebuild drill",
    "Upload coverage to Codecov",
    "Dependency audit",
    "Compose config validation",
    "Container build validation",
)
FORBIDDEN_TRACKED_PREFIXES = (
    ".freemail-qa/",
    ".venv/",
    "data/",
    "maildata/",
    "secrets/",
    "node_modules/",
    "dist/",
    "build/",
)
RELEASE_BLOCKERS = (
    "controlled-domain DNS/mail-flow/private-beta evidence",
    "live Stalwart apply evidence for the controlled domain",
    "real signed native mobile builds",
    "real store-submission evidence",
    "app-store release execution",
    "final private-beta decision acceptance",
)


@dataclass(frozen=True)
class OpenSourceReadinessOptions:
    root: Path = Path.cwd()


def check_open_source_readiness(options: OpenSourceReadinessOptions) -> dict[str, Any]:
    root = options.root.resolve()
    checks = [
        _required_files_check(root),
        _gitignore_check(root),
        _tracked_files_check(root),
        _repo_secret_scan_check(root),
        _license_policy_check(root),
        _ci_workflow_check(root),
        _mobile_package_check(root),
        _release_boundary_check(root),
    ]
    passed = all(check["status"] == "pass" for check in checks)
    return {
        "passed": passed,
        "project": "FreeMail",
        "license": "AGPL-3.0-or-later",
        "credentialFreePublicRepo": passed,
        "checks": checks,
        "releaseReady": False,
        "releaseBlockers": list(RELEASE_BLOCKERS),
    }


def _required_files_check(root: Path) -> dict[str, Any]:
    missing = []
    content_failures = []
    for relative_path, required_markers in REQUIRED_FILES.items():
        path = root / relative_path
        if not path.is_file():
            missing.append(relative_path)
            continue
        content = path.read_text(encoding="utf-8", errors="ignore").lower()
        missing_markers = [marker for marker in required_markers if marker.lower() not in content]
        if missing_markers:
            content_failures.append({"file": relative_path, "missingMarkers": missing_markers})
    return _check(
        "required-public-files",
        not missing and not content_failures,
        {"missing": missing, "contentFailures": content_failures},
    )


def _gitignore_check(root: Path) -> dict[str, Any]:
    content = (root / ".gitignore").read_text(encoding="utf-8", errors="ignore")
    required = [".env", ".freemail-qa/", "data/", "secrets/", "*.pem", "*.key", "*.p12"]
    missing = [pattern for pattern in required if pattern not in content]
    return _check("gitignore-secret-boundaries", not missing, {"missingPatterns": missing})


def _tracked_files_check(root: Path) -> dict[str, Any]:
    files = _tracked_files(root)
    forbidden = [
        path
        for path in files
        if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in FORBIDDEN_TRACKED_PREFIXES)
    ]
    return _check("tracked-file-boundaries", not forbidden, {"forbiddenTrackedFiles": forbidden})


def _repo_secret_scan_check(root: Path) -> dict[str, Any]:
    failures = scan_repo(root)
    return _check("repo-secret-scan", not failures, {"failures": failures})


def _license_policy_check(root: Path) -> dict[str, Any]:
    failures = scan_license_policy(root)
    return _check("license-policy-scan", not failures, {"failures": failures})


def _ci_workflow_check(root: Path) -> dict[str, Any]:
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8", errors="ignore")
    missing = [step for step in REQUIRED_CI_STEPS if step not in workflow]
    return _check("ci-publication-gates", not missing, {"missingSteps": missing})


def _mobile_package_check(root: Path) -> dict[str, Any]:
    package = json.loads((root / "apps" / "mobile" / "package.json").read_text(encoding="utf-8"))
    failures = []
    if package.get("license") != "AGPL-3.0-or-later":
        failures.append("mobile package must declare AGPL-3.0-or-later")
    if not package.get("private"):
        failures.append("mobile package should remain private for npm publishing until release packaging is explicit")
    return _check("mobile-package-metadata", not failures, {"failures": failures})


def _release_boundary_check(root: Path) -> dict[str, Any]:
    readme = (root / "README.md").read_text(encoding="utf-8", errors="ignore").lower()
    release_notes = (root / "docs" / "release-notes" / "v0.1.0-private-beta.md").read_text(
        encoding="utf-8",
        errors="ignore",
    ).lower()
    required_terms = ("vpn-only", "private-beta", "known limitations")
    missing = [term for term in required_terms if term not in readme and term not in release_notes]
    return _check("release-boundary-disclosure", not missing, {"missingTerms": missing})


def _tracked_files(root: Path) -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=False,
    ).stdout
    return sorted(item.decode("utf-8").replace("\\", "/") for item in output.split(b"\0") if item)


def _check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "details": details}
