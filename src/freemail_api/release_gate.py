from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any
from urllib.request import urlopen


class ReleaseGateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseGateOptions:
    repo: str = "CYINT/freemail"
    remote: str = "origin"
    branch: str = "main"
    health_url: str | None = "https://freemail.kuzuryu.ai/health"
    deployment_url: str | None = "https://freemail.kuzuryu.ai/api/v1/deployment"
    metadata_readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/metadata/readiness"
    readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/mail-core/readiness"
    metadata_backup: Path | None = None
    mail_store_backup: Path | None = None
    mobile_release_evidence: Path | None = None
    mobile_app_config: Path = Path("apps/mobile/app.json")
    private_beta_evidence: Path | None = None
    release_notes: Path | None = None
    release_version: str | None = None
    skip_github_ci: bool = False
    skip_backup_evidence: bool = False
    skip_mobile_evidence: bool = False
    skip_private_beta_evidence: bool = False
    require_mobile_store_submission: bool = False
    skip_release_notes: bool = False
    skip_runtime: bool = False


def run_release_gate(options: ReleaseGateOptions) -> dict[str, Any]:
    commit = _command(["git", "rev-parse", "HEAD"])
    checks = [
        _check_clean_git(),
        _check_remote_commit(options.remote, options.branch, commit),
        _check_compose_config(),
    ]
    if not options.skip_github_ci:
        checks.append(_check_github_ci(options.repo, commit))
    if not options.skip_backup_evidence:
        checks.extend(_check_backup_evidence(options.metadata_backup, options.mail_store_backup))
    if not options.skip_mobile_evidence:
        checks.append(
            _check_mobile_release_evidence(
                options.mobile_release_evidence,
                options.mobile_app_config,
                require_store_submission=options.require_mobile_store_submission,
            )
        )
    if not options.skip_private_beta_evidence:
        checks.append(_check_private_beta_evidence(options.private_beta_evidence))
    if not options.skip_release_notes:
        checks.append(_check_release_notes(options.release_notes, options.release_version))
    if not options.skip_runtime:
        checks.extend(
            _check_runtime(
                options.health_url,
                options.deployment_url,
                options.readiness_url,
                commit,
                metadata_readiness_url=options.metadata_readiness_url,
            )
        )

    passed = all(check["status"] == "pass" for check in checks)
    return {
        "passed": passed,
        "commit": commit,
        "repo": options.repo,
        "checks": checks,
    }


def assert_release_gate(options: ReleaseGateOptions) -> dict[str, Any]:
    result = run_release_gate(options)
    if not result["passed"]:
        failed = ", ".join(check["name"] for check in result["checks"] if check["status"] != "pass")
        raise ReleaseGateError(f"release gate failed: {failed}")
    return result


def _check_clean_git() -> dict[str, Any]:
    status = _command(["git", "status", "--short"])
    return _check("git-clean", status == "", {"dirty": bool(status)})


def _check_remote_commit(remote: str, branch: str, commit: str) -> dict[str, Any]:
    remote_ref = f"refs/heads/{branch}"
    output = _command(["git", "ls-remote", remote, remote_ref])
    remote_commit = output.split()[0] if output else ""
    return _check(
        "remote-sha",
        remote_commit == commit,
        {"remote": remote, "branch": branch, "remoteCommit": remote_commit, "expectedCommit": commit},
    )


def _check_compose_config() -> dict[str, Any]:
    _command(["docker", "compose", "config", "--quiet"])
    return _check("compose-config", True, {})


def _check_github_ci(repo: str, commit: str) -> dict[str, Any]:
    output = _command(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--commit",
            commit,
            "--limit",
            "10",
            "--json",
            "databaseId,status,conclusion,workflowName,url",
        ]
    )
    runs = json.loads(output)
    ci_runs = [run for run in runs if run.get("workflowName") == "CI"]
    latest = ci_runs[0] if ci_runs else None
    passed = bool(latest and latest.get("status") == "completed" and latest.get("conclusion") == "success")
    return _check("github-ci", passed, {"latestRun": latest})


def _check_backup_evidence(
    metadata_backup: Path | None,
    mail_store_backup: Path | None,
) -> list[dict[str, Any]]:
    if metadata_backup is None or mail_store_backup is None:
        return [_check("backup-evidence", False, {"error": "metadata and mail-store backup paths are required"})]
    return [
        _check_backup_file("metadata-backup", metadata_backup),
        _check_backup_file("mail-store-backup", mail_store_backup),
    ]


def _check_backup_file(name: str, path: Path) -> dict[str, Any]:
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    return _check(name, exists and size > 0, _file_evidence_details(path, exists, size))


def _check_mobile_release_evidence(
    path: Path | None,
    app_config: Path,
    *,
    require_store_submission: bool,
) -> dict[str, Any]:
    if path is None:
        return _check("mobile-release-evidence", False, {"error": "mobile release evidence path is required"})
    from .mobile_release_gate import MobileReleaseGateOptions, run_mobile_release_gate

    result = run_mobile_release_gate(
        MobileReleaseGateOptions(
            evidence=path,
            app_config=app_config,
            require_store_submission=require_store_submission,
        )
    )
    failed = [check["name"] for check in result["checks"] if check["status"] != "pass"]
    return _check(
        "mobile-release-evidence",
        bool(result["passed"]),
        {
            "path": str(path),
            "requireStoreSubmission": require_store_submission,
            "failedChecks": failed,
            "evidenceDetails": result["evidenceDetails"],
        },
    )


def _check_private_beta_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _check("private-beta-evidence", False, {"error": "private-beta gate output path is required"})
    payload = _load_json_file(path)
    checks = payload.get("checks")
    check_names = [check.get("name") for check in checks if isinstance(check, dict)] if isinstance(checks, list) else []
    required_checks = {
        "controlled-domain-dns",
        "controlled-mail-flow-evidence",
        "queue-evidence",
        "mail-core-apply-evidence",
        "deliverability-abuse-evidence",
        "metadata-backup-evidence",
        "mail-store-backup-evidence",
        "private-beta-acceptance",
    }
    details = _file_evidence_details(path)
    details.update(
        {
            "domain": payload.get("domain"),
            "passed": payload.get("passed"),
            "missingChecks": sorted(required_checks.difference(check_names)),
            "failedChecks": [
                check.get("name")
                for check in checks
                if isinstance(check, dict) and check.get("status") != "pass"
            ]
            if isinstance(checks, list)
            else ["checks"],
        }
    )
    passed = (
        payload.get("passed") is True
        and bool(str(payload.get("domain", "")).strip())
        and isinstance(checks, list)
        and not details["missingChecks"]
        and not details["failedChecks"]
    )
    return _check("private-beta-evidence", passed, details)


def _check_release_notes(path: Path | None, release_version: str | None) -> dict[str, Any]:
    if path is None:
        return _check("release-notes", False, {"error": "release notes path is required"})
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    details = _file_evidence_details(path, exists, size)
    if not exists or size == 0:
        details["error"] = "release notes file must exist and be non-empty"
        return _check("release-notes", False, details)

    content = path.read_text(encoding="utf-8").strip()
    lowered = content.lower()
    required_terms = ["freemail", "verification", "known limitations", "vpn"]
    missing_terms = [term for term in required_terms if term not in lowered]
    placeholder_terms = ["todo", "tbd", "fixme", "changeme", "placeholder"]
    placeholders = [term for term in placeholder_terms if term in lowered]
    normalized_version = (release_version or "").strip()
    version_present = not normalized_version or normalized_version.lower() in lowered
    details.update(
        {
            "version": normalized_version or None,
            "versionPresent": version_present,
            "missingRequiredTerms": missing_terms,
            "placeholderTerms": placeholders,
        }
    )
    return _check("release-notes", version_present and not missing_terms and not placeholders, details)


def _load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ReleaseGateError(f"{path} must contain a JSON object")
    return payload


def _file_evidence_details(path: Path, exists: bool | None = None, size: int | None = None) -> dict[str, Any]:
    resolved_exists = path.is_file() if exists is None else exists
    resolved_size = path.stat().st_size if size is None and resolved_exists else (size or 0)
    details: dict[str, Any] = {"path": str(path), "bytes": resolved_size}
    if resolved_exists and resolved_size > 0:
        details["sha256"] = _sha256_file(path)
    return details


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_runtime(
    health_url: str | None,
    deployment_url: str | None,
    readiness_url: str | None,
    commit: str,
    *,
    metadata_readiness_url: str | None = None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if health_url:
        health = _fetch_json(health_url)
        release = health.get("release") if isinstance(health.get("release"), dict) else {}
        checks.append(
            _check(
                "runtime-health",
                health.get("status") == "ok"
                and health.get("vpnOnly") is True
                and release.get("commit") in {commit, "unknown"},
                {
                    "url": health_url,
                    "status": health.get("status"),
                    "vpnOnly": health.get("vpnOnly"),
                    "releaseCommit": release.get("commit"),
                },
            )
        )
    if deployment_url:
        deployment = _fetch_json(deployment_url)
        checks.append(
            _check(
                "deployment-boundary",
                deployment.get("exposure") == "vpn-only"
                and deployment.get("publicInternet") is False
                and str(deployment.get("requiredBoundary", "")).lower().find("vpn") >= 0,
                {
                    "url": deployment_url,
                    "exposure": deployment.get("exposure"),
                    "publicInternet": deployment.get("publicInternet"),
                    "requiredBoundary": deployment.get("requiredBoundary"),
                },
            )
        )
    if metadata_readiness_url:
        metadata = _fetch_json(metadata_readiness_url)
        checks.append(
            _check(
                "metadata-readiness",
                metadata.get("status") == "ready"
                and metadata.get("backend") == "sqlite"
                and bool(str(metadata.get("schemaRevision", "")).strip())
                and _checks_passed(metadata.get("checks")),
                {
                    "url": metadata_readiness_url,
                    "status": metadata.get("status"),
                    "backend": metadata.get("backend"),
                    "schemaRevision": metadata.get("schemaRevision"),
                    "checks": metadata.get("checks"),
                },
            )
        )
    if readiness_url:
        readiness = _fetch_json(readiness_url)
        checks.append(
            _check(
                "mail-core-readiness",
                readiness.get("status") == "ready"
                and readiness.get("tcpReachable") is True
                and readiness.get("protocolReady") is True,
                {
                    "url": readiness_url,
                    "status": readiness.get("status"),
                    "tcpReachable": readiness.get("tcpReachable"),
                    "protocolReady": readiness.get("protocolReady"),
                },
            )
        )
    return checks


def _checks_passed(checks: object) -> bool:
    return isinstance(checks, list) and bool(checks) and all(
        isinstance(check, dict) and check.get("status") == "pass" for check in checks
    )


def _fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=10) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ReleaseGateError(f"{url} did not return a JSON object")
    return data


def _check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "details": details}


def _command(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        stderr = error.stderr.strip() if error.stderr else str(error)
        raise ReleaseGateError(f"{command[0]} command failed: {stderr}") from error
    return result.stdout.strip()
