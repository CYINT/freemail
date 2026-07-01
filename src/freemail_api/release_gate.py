from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.request import urlopen


class ReleaseGateError(RuntimeError):
    pass


REQUIRED_CI_STEPS = (
    "Lint",
    "Repository secret scan",
    "License policy scan",
    "Open-source readiness",
    "Tests",
    "Browser webmail QA",
    "Mobile static QA",
    "Mobile dependency install",
    "Mobile config validation",
    "Mobile native prebuild drill",
    "Mobile typecheck",
    "Mobile dependency audit",
    "Dependency audit",
    "Compose config validation",
    "Container build validation",
)

EXPECTED_IOS_APP_ID = "technology.cyint.freemail"
EXPECTED_ANDROID_PACKAGE = "technology.cyint.freemail"
ANDROID_SHA256_FINGERPRINT_PATTERN = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){31}$")


@dataclass(frozen=True)
class ReleaseGateOptions:
    repo: str = "CYINT/freemail"
    remote: str = "origin"
    branch: str = "main"
    health_url: str | None = "https://freemail.kuzuryu.ai/health"
    deployment_url: str | None = "https://freemail.kuzuryu.ai/api/v1/deployment"
    product_readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/product/readiness"
    metadata_readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/metadata/readiness"
    readiness_url: str | None = "https://freemail.kuzuryu.ai/api/v1/mail-core/readiness"
    apple_app_site_association_url: str | None = "https://freemail.kuzuryu.ai/.well-known/apple-app-site-association"
    assetlinks_url: str | None = "https://freemail.kuzuryu.ai/.well-known/assetlinks.json"
    metadata_backup: Path | None = None
    mail_store_backup: Path | None = None
    restore_drill_evidence: Path | None = None
    mobile_release_evidence: Path | None = None
    mobile_app_config: Path = Path("apps/mobile/app.json")
    private_beta_evidence: Path | None = None
    release_notes: Path | None = None
    release_version: str | None = None
    skip_github_ci: bool = False
    skip_ci_step_provenance: bool = False
    skip_codecov_upload: bool = False
    skip_repo_secret_scan: bool = False
    skip_license_policy_scan: bool = False
    skip_open_source_readiness: bool = False
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
        _check_compose_loopback_bindings(),
    ]
    if not options.skip_repo_secret_scan:
        checks.append(_check_repo_secret_scan())
    if not options.skip_license_policy_scan:
        checks.append(_check_license_policy_scan())
    if not options.skip_open_source_readiness:
        checks.append(_check_open_source_readiness())
    if not options.skip_github_ci:
        checks.append(_check_github_ci(options.repo, commit))
        if not options.skip_ci_step_provenance:
            checks.append(_check_ci_required_steps(options.repo, commit))
        if not options.skip_codecov_upload:
            checks.append(_check_codecov_upload(options.repo, commit))
    if not options.skip_backup_evidence:
        checks.extend(
            _check_backup_evidence(options.metadata_backup, options.mail_store_backup, options.restore_drill_evidence)
        )
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
                product_readiness_url=options.product_readiness_url,
                apple_app_site_association_url=options.apple_app_site_association_url,
                assetlinks_url=options.assetlinks_url,
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


def _check_compose_loopback_bindings() -> dict[str, Any]:
    output = _command(["docker", "compose", "--profile", "web", "--profile", "mail-core", "config", "--format", "json"])
    payload = json.loads(output)
    services = payload.get("services") if isinstance(payload, dict) else None
    bindings: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    if isinstance(services, dict):
        for service_name, service in sorted(services.items()):
            ports = service.get("ports") if isinstance(service, dict) else None
            if not isinstance(ports, list):
                continue
            for port in ports:
                if not isinstance(port, dict):
                    continue
                binding = {
                    "service": service_name,
                    "hostIp": port.get("host_ip"),
                    "published": str(port.get("published", "")),
                    "target": port.get("target"),
                    "protocol": port.get("protocol", "tcp"),
                }
                bindings.append(binding)
                if not _is_loopback_host_ip(port.get("host_ip")):
                    violations.append(binding)
    return _check(
        "compose-loopback-bindings",
        not violations,
        {
            "profiles": ["web", "mail-core"],
            "bindings": bindings,
            "violations": violations,
        },
    )


def _is_loopback_host_ip(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"127.0.0.1", "::1", "localhost"}


def _check_github_ci(repo: str, commit: str) -> dict[str, Any]:
    latest = _latest_ci_run(repo, commit)
    passed = bool(latest and latest.get("status") == "completed" and latest.get("conclusion") == "success")
    return _check("github-ci", passed, {"latestRun": latest})


def _check_codecov_upload(repo: str, commit: str) -> dict[str, Any]:
    latest = _latest_ci_run(repo, commit)
    if not latest or latest.get("status") != "completed" or latest.get("conclusion") != "success":
        return _check("codecov-upload", False, {"error": "passing CI run is required", "latestRun": latest})
    matching_steps: list[dict[str, Any]] = []
    for job in _ci_run_jobs(repo, latest["databaseId"]):
        for step in _job_steps(job):
            if step.get("name") == "Upload coverage to Codecov":
                matching_steps.append(_step_details(job, step))
    passed = any(step.get("status") == "completed" and step.get("conclusion") == "success" for step in matching_steps)
    return _check("codecov-upload", passed, {"latestRun": latest, "steps": matching_steps})


def _check_ci_required_steps(repo: str, commit: str) -> dict[str, Any]:
    latest = _latest_ci_run(repo, commit)
    if not latest or latest.get("status") != "completed" or latest.get("conclusion") != "success":
        return _check("ci-required-steps", False, {"error": "passing CI run is required", "latestRun": latest})
    observed_steps = {
        str(step.get("name")): _step_details(job, step)
        for job in _ci_run_jobs(repo, latest["databaseId"])
        for step in _job_steps(job)
    }
    missing = [name for name in REQUIRED_CI_STEPS if name not in observed_steps]
    failed = [
        name
        for name in REQUIRED_CI_STEPS
        if name in observed_steps
        and (
            observed_steps[name].get("status") != "completed"
            or observed_steps[name].get("conclusion") != "success"
        )
    ]
    return _check(
        "ci-required-steps",
        not missing and not failed,
        {
            "latestRun": latest,
            "requiredSteps": list(REQUIRED_CI_STEPS),
            "missingSteps": missing,
            "failedSteps": failed,
        },
    )


def _latest_ci_run(repo: str, commit: str) -> dict[str, Any] | None:
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
    return ci_runs[0] if ci_runs else None


def _ci_run_jobs(repo: str, run_id: object) -> list[dict[str, Any]]:
    output = _command(["gh", "run", "view", str(run_id), "--repo", repo, "--json", "jobs"])
    payload = json.loads(output)
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    return [job for job in jobs if isinstance(job, dict)] if isinstance(jobs, list) else []


def _job_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job.get("steps")
    return [step for step in steps if isinstance(step, dict)] if isinstance(steps, list) else []


def _step_details(job: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    return {
        "job": job.get("name"),
        "name": step.get("name"),
        "status": step.get("status"),
        "conclusion": step.get("conclusion"),
    }


def _check_repo_secret_scan() -> dict[str, Any]:
    _command([sys.executable, "scripts/qa_repo_secrets.py"])
    return _check("repo-secret-scan", True, {"script": "scripts/qa_repo_secrets.py"})


def _check_license_policy_scan() -> dict[str, Any]:
    _command([sys.executable, "scripts/qa_license_policy.py"])
    return _check("license-policy-scan", True, {"script": "scripts/qa_license_policy.py"})


def _check_open_source_readiness() -> dict[str, Any]:
    from .open_source_readiness import OpenSourceReadinessOptions, check_open_source_readiness

    result = check_open_source_readiness(OpenSourceReadinessOptions(root=Path.cwd()))
    failed = [check["name"] for check in result["checks"] if check["status"] != "pass"]
    return _check(
        "open-source-readiness",
        bool(result["passed"]),
        {
            "credentialFreePublicRepo": result["credentialFreePublicRepo"],
            "license": result["license"],
            "releaseReady": result["releaseReady"],
            "releaseBlockers": result["releaseBlockers"],
            "failedChecks": failed,
        },
    )


def _check_backup_evidence(
    metadata_backup: Path | None,
    mail_store_backup: Path | None,
    restore_drill_evidence: Path | None,
) -> list[dict[str, Any]]:
    if metadata_backup is None or mail_store_backup is None or restore_drill_evidence is None:
        return [
            _check(
                "backup-evidence",
                False,
                {"error": "metadata, mail-store, and restore-drill evidence paths are required"},
            )
        ]
    return [
        _check_backup_file("metadata-backup", metadata_backup),
        _check_backup_file("mail-store-backup", mail_store_backup),
        _check_restore_drill_evidence(restore_drill_evidence),
    ]


def _check_backup_file(name: str, path: Path) -> dict[str, Any]:
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    return _check(name, exists and size > 0, _file_evidence_details(path, exists, size))


def _check_restore_drill_evidence(path: Path) -> dict[str, Any]:
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    details = _file_evidence_details(path, exists, size)
    if not exists or size == 0:
        details["error"] = "restore drill evidence file must exist and be non-empty"
        return _check("restore-drill-evidence", False, details)
    payload = _load_json_file(path)
    metadata_restore = payload.get("metadataRestore") if isinstance(payload.get("metadataRestore"), dict) else {}
    mail_store_restore = payload.get("mailStoreRestore") if isinstance(payload.get("mailStoreRestore"), dict) else {}
    apply_plan = payload.get("stalwartApplyPlan") if isinstance(payload.get("stalwartApplyPlan"), dict) else {}
    details.update(
        {
            "credentialFree": payload.get("credentialFree"),
            "metadataRestored": metadata_restore.get("restored"),
            "mailStoreRestored": mail_store_restore.get("restored"),
            "stalwartApplyPlanExported": apply_plan.get("exported"),
        }
    )
    passed = (
        payload.get("credentialFree") is True
        and metadata_restore.get("restored") is True
        and mail_store_restore.get("restored") is True
        and apply_plan.get("exported") is True
    )
    return _check("restore-drill-evidence", passed, details)


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
        "restore-drill-evidence",
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
    product_readiness_url: str | None = None,
    apple_app_site_association_url: str | None = None,
    assetlinks_url: str | None = None,
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
                and release.get("commit") == commit,
                {
                    "url": health_url,
                    "status": health.get("status"),
                    "vpnOnly": health.get("vpnOnly"),
                    "releaseCommit": release.get("commit"),
                },
            )
        )
        checks.append(_check_security_headers(health_url))
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
    if product_readiness_url:
        product = _fetch_json(product_readiness_url)
        components = product.get("components") if isinstance(product.get("components"), dict) else {}
        component_statuses = {
            name: component.get("status")
            for name, component in components.items()
            if isinstance(component, dict)
        }
        expected_statuses = {
            "adminApi": "ready",
            "mailCore": "runtime-ready",
            "webmail": "beta-ready",
            "mobile": "source-ready",
        }
        release_blockers = product.get("releaseBlockers")
        checks.append(
            _check(
                "product-readiness",
                product.get("project") == "FreeMail"
                and product.get("license") == "AGPL-3.0-or-later"
                and product.get("credentialFreePublicRepo") is True
                and product.get("vpnOnly") is True
                and product.get("releaseReady") is False
                and component_statuses == expected_statuses
                and isinstance(release_blockers, list)
                and bool(release_blockers)
                and "real signed native mobile builds" in release_blockers,
                {
                    "url": product_readiness_url,
                    "project": product.get("project"),
                    "license": product.get("license"),
                    "credentialFreePublicRepo": product.get("credentialFreePublicRepo"),
                    "vpnOnly": product.get("vpnOnly"),
                    "releaseReady": product.get("releaseReady"),
                    "componentStatuses": component_statuses,
                    "releaseBlockers": release_blockers,
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
    if apple_app_site_association_url:
        checks.append(_check_apple_app_site_association(apple_app_site_association_url))
    if assetlinks_url:
        checks.append(_check_assetlinks(assetlinks_url))
    return checks


def _check_apple_app_site_association(url: str) -> dict[str, Any]:
    document = _fetch_json(url)
    applinks = document.get("applinks") if isinstance(document.get("applinks"), dict) else {}
    details = applinks.get("details") if isinstance(applinks.get("details"), list) else []
    app_ids = [
        str(app_id)
        for detail in details
        if isinstance(detail, dict)
        for app_id in [detail.get("appID")]
        if isinstance(app_id, str)
    ]
    has_valid_app_id = any(_valid_ios_app_id(app_id) for app_id in app_ids)
    has_invite_component = any(_aasa_detail_has_invite_component(detail) for detail in details if isinstance(detail, dict))
    return _check(
        "mobile-apple-app-site-association",
        applinks.get("apps") == [] and has_valid_app_id and has_invite_component,
        {
            "url": url,
            "apps": applinks.get("apps"),
            "appIDs": app_ids,
            "expectedBundleID": EXPECTED_IOS_APP_ID,
            "hasInviteComponent": has_invite_component,
        },
    )


def _check_assetlinks(url: str) -> dict[str, Any]:
    document = _fetch_json_value(url)
    entries = document if isinstance(document, list) else []
    package_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("target"), dict)
        and entry["target"].get("namespace") == "android_app"
        and entry["target"].get("package_name") == EXPECTED_ANDROID_PACKAGE
    ]
    fingerprints = [
        str(fingerprint)
        for entry in package_entries
        for fingerprint in entry["target"].get("sha256_cert_fingerprints", [])
        if isinstance(fingerprint, str)
    ]
    relations = {
        str(relation)
        for entry in package_entries
        for relation in entry.get("relation", [])
        if isinstance(relation, str)
    }
    valid_fingerprints = [fingerprint for fingerprint in fingerprints if ANDROID_SHA256_FINGERPRINT_PATTERN.match(fingerprint)]
    return _check(
        "mobile-android-assetlinks",
        bool(package_entries)
        and "delegate_permission/common.handle_all_urls" in relations
        and bool(valid_fingerprints)
        and len(valid_fingerprints) == len(fingerprints),
        {
            "url": url,
            "packageName": EXPECTED_ANDROID_PACKAGE,
            "entryCount": len(package_entries),
            "relations": sorted(relations),
            "fingerprintCount": len(fingerprints),
            "validFingerprintCount": len(valid_fingerprints),
        },
    )


def _aasa_detail_has_invite_component(detail: dict[str, Any]) -> bool:
    components = detail.get("components")
    if not isinstance(components, list):
        return False
    for component in components:
        if not isinstance(component, dict):
            continue
        query = component.get("?")
        if isinstance(query, dict) and "invite" in query:
            return True
    return False


def _valid_ios_app_id(app_id: str) -> bool:
    if not app_id.endswith(f".{EXPECTED_IOS_APP_ID}") or "." not in app_id:
        return False
    team_id = app_id.split(".", 1)[0]
    return len(team_id) == 10 and team_id.isalnum() and team_id.isupper()


def _check_security_headers(url: str) -> dict[str, Any]:
    headers = _fetch_headers(url)
    expected = {
        "content-security-policy": ["default-src 'self'", "frame-ancestors 'none'", "object-src 'none'"],
        "cross-origin-opener-policy": ["same-origin"],
        "permissions-policy": ["camera=()", "microphone=()", "geolocation=()"],
        "referrer-policy": ["no-referrer"],
        "x-content-type-options": ["nosniff"],
        "x-frame-options": ["DENY"],
    }
    missing: dict[str, list[str]] = {}
    observed: dict[str, str | None] = {}
    for header, required_fragments in expected.items():
        value = headers.get(header)
        observed[header] = value
        missing_fragments = [fragment for fragment in required_fragments if fragment.lower() not in str(value or "").lower()]
        if missing_fragments:
            missing[header] = missing_fragments
    return _check(
        "runtime-security-headers",
        not missing,
        {
            "url": url,
            "observed": observed,
            "missing": missing,
        },
    )


def _checks_passed(checks: object) -> bool:
    return isinstance(checks, list) and bool(checks) and all(
        isinstance(check, dict) and check.get("status") == "pass" for check in checks
    )


def _fetch_json(url: str) -> dict[str, Any]:
    data = _fetch_json_value(url)
    if not isinstance(data, dict):
        raise ReleaseGateError(f"{url} did not return a JSON object")
    return data


def _fetch_json_value(url: str) -> Any:
    with urlopen(url, timeout=10) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _fetch_headers(url: str) -> dict[str, str]:
    with urlopen(url, timeout=10) as response:
        return {str(name).lower(): str(value) for name, value in response.headers.items()}


def _check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "details": details}


def _command(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        stderr = error.stderr.strip() if error.stderr else str(error)
        raise ReleaseGateError(f"{command[0]} command failed: {stderr}") from error
    return result.stdout.strip()
