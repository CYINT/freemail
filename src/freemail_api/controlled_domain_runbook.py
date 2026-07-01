from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .mobile_release_evidence import MOBILE_EVIDENCE_DOMAIN_FILENAME
from .private_beta_evidence import EVIDENCE_FILENAMES, _normalize_domain


@dataclass(frozen=True)
class ControlledDomainRunbookOptions:
    domain: str
    output: Path
    evidence_dir: Path
    database: Path = Path("data/freemail.sqlite")
    admin_email: str | None = None
    admin_display_name: str = "FreeMail Administrator"
    admin_password_env: str = "FREEMAIL_PRIVATE_BETA_ADMIN_PASSWORD"
    hostname: str = "freemail.kuzuryu.ai"
    secrets_json: Path = Path("secrets/mail-core-users.json")
    release_version: str = "v0.1.0-private-beta"
    release_notes: Path = Path("docs/release-notes/v0.1.0-private-beta.md")
    mobile_release_evidence: Path | None = None
    backup_dir: Path | None = None
    force: bool = False
    generated_at: datetime | None = None
    write_markdown: bool = False


def create_controlled_domain_runbook(options: ControlledDomainRunbookOptions) -> dict[str, Any]:
    domain = _normalize_domain(options.domain)
    generated_at = _format_timestamp(options.generated_at or datetime.now(timezone.utc))
    evidence_dir = options.evidence_dir
    backup_dir = options.backup_dir or evidence_dir / "backups"
    admin_email = (options.admin_email or f"admin@{domain}").strip().lower()
    if admin_email.partition("@")[2] != domain:
        raise ValueError("admin email domain must match controlled domain")

    paths = _artifact_paths(domain, evidence_dir, backup_dir)
    runbook = {
        "domain": domain,
        "generatedAt": generated_at,
        "credentialFree": True,
        "vpnBoundary": "Dragonscale/VPN clients only",
        "paths": {key: str(value) for key, value in paths.items()},
        "environment": {
            "adminPasswordEnv": options.admin_password_env,
            "hostname": options.hostname,
            "database": str(options.database),
            "secretsJson": str(options.secrets_json),
        },
        "commands": _commands(
            domain=domain,
            admin_email=admin_email,
            admin_display_name=options.admin_display_name,
            options=options,
            paths=paths,
        ),
        "remainingManualInputs": [
            "Set the admin password environment variable from a password manager before provisioning.",
            "Publish MX, SPF, DMARC, and DKIM DNS records from provisioning output.",
            "Wait for DNS propagation before controlled mail-flow collection.",
            "Run signed mobile build and store-submission evidence collection in the private signing/store environments.",
            "Record decision-owner acceptance only after controlled-domain evidence and known limitations are reviewed.",
        ],
    }
    _write_json(options.output, runbook, force=options.force)
    markdown_path = None
    if options.write_markdown:
        markdown_path = options.output.with_suffix(".md")
        _write_text(markdown_path, _markdown(runbook), force=options.force)
    return {
        "domain": domain,
        "file": str(options.output),
        "markdown": str(markdown_path) if markdown_path else None,
        "generatedAt": generated_at,
        "credentialFree": True,
    }


def _artifact_paths(domain: str, evidence_dir: Path, backup_dir: Path) -> dict[str, Path]:
    return {
        "evidenceDir": evidence_dir,
        "privateBetaManifest": evidence_dir / EVIDENCE_FILENAMES["manifest"].format(domain=domain),
        "dnsGuidance": evidence_dir / f"dns-guidance.{domain}.json",
        "privateBetaGate": evidence_dir / f"private-beta-gate.{domain}.json",
        "releaseManifest": evidence_dir / f"release-evidence-manifest.{domain}.json",
        "releaseGate": evidence_dir / f"release-gate.{domain}.json",
        "metadataBackup": backup_dir / EVIDENCE_FILENAMES["metadata_backup"].format(domain=domain),
        "mailStoreBackup": backup_dir / EVIDENCE_FILENAMES["mail_store_backup"].format(domain=domain),
        "restoreDrillEvidence": backup_dir / EVIDENCE_FILENAMES["restore_drill_evidence"].format(domain=domain),
    }


def _commands(
    *,
    domain: str,
    admin_email: str,
    admin_display_name: str,
    options: ControlledDomainRunbookOptions,
    paths: dict[str, Path],
) -> list[dict[str, Any]]:
    mobile_evidence = options.mobile_release_evidence or Path(".freemail-qa") / MOBILE_EVIDENCE_DOMAIN_FILENAME
    return [
        _command(
            "create-draft-private-beta-packet",
            "Create credential-free draft private-beta evidence templates.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\create_private_beta_evidence_templates.py",
                "--domain",
                domain,
                "--output-dir",
                str(paths["evidenceDir"]),
                "--force",
            ],
        ),
        _command(
            "provision-controlled-domain",
            "Create or reuse controlled-domain metadata, DKIM, mailbox, and ignored mail-core account secret.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\provision_controlled_domain.py",
                "--database",
                str(options.database),
                "--domain",
                domain,
                "--admin-email",
                admin_email,
                "--admin-display-name",
                admin_display_name,
                "--admin-initial-password-env",
                options.admin_password_env,
                "--hostname",
                options.hostname,
                "--secrets-json",
                str(options.secrets_json),
            ],
            output=paths["dnsGuidance"],
        ),
        _command(
            "collect-mail-core-apply-evidence",
            "Apply Stalwart metadata and write credential-free apply evidence.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\collect_stalwart_apply_evidence.py",
                "--domain",
                domain,
                "--database",
                str(options.database),
                "--secrets-json",
                str(options.secrets_json),
                "--output",
                str(paths["evidenceDir"] / EVIDENCE_FILENAMES["mail_core_apply"].format(domain=domain)),
                "--force",
            ],
        ),
        _command(
            "collect-controlled-domain-evidence",
            "Collect observed DNS, mail-flow, queue, and deliverability evidence after DNS propagates.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\collect_controlled_domain_evidence.py",
                "--domain",
                domain,
                "--output-dir",
                str(paths["evidenceDir"]),
                "--email",
                admin_email,
                "--secrets-json",
                str(options.secrets_json),
                "--dns-guidance",
                str(paths["dnsGuidance"]),
                "--spf-aligned",
                "--dmarc-aligned",
                "--bounce-or-retry-reviewed",
                "--abuse-complaints",
                "0",
                "--force",
            ],
        ),
        _command(
            "collect-private-beta-acceptance",
            "Record decision-owner acceptance after reviewing the completed packet.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\collect_private_beta_acceptance.py",
                "--domain",
                domain,
                "--output",
                str(paths["evidenceDir"] / EVIDENCE_FILENAMES["acceptance"].format(domain=domain)),
                "--decision-owner",
                "Decision Owner",
                "--accepted",
                "--force",
            ],
        ),
        _command(
            "check-private-beta-packet",
            "Check private-beta packet inventory before running the hard private-beta gate.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\private_beta_packet_status.py",
                "--manifest",
                str(paths["privateBetaManifest"]),
            ],
        ),
        _command(
            "run-private-beta-gate",
            "Run private-beta gate and preserve its output outside Git.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\private_beta_gate.py",
                "--manifest",
                str(paths["privateBetaManifest"]),
            ],
            output=paths["privateBetaGate"],
        ),
        _command(
            "create-release-evidence-manifest",
            "Create the top-level release evidence manifest after backup/mobile/private-beta artifacts exist.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\create_release_evidence_manifest.py",
                "--output",
                str(paths["releaseManifest"]),
                "--metadata-backup",
                str(paths["metadataBackup"]),
                "--mail-store-backup",
                str(paths["mailStoreBackup"]),
                "--restore-drill-evidence",
                str(paths["restoreDrillEvidence"]),
                "--mobile-release-evidence",
                str(mobile_evidence),
                "--private-beta-evidence",
                str(paths["privateBetaGate"]),
                "--release-notes",
                str(options.release_notes),
                "--release-version",
                options.release_version,
                "--force",
            ],
        ),
        _command(
            "check-release-packet",
            "Check top-level release packet inventory before the hard release gate.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\release_packet_status.py",
                "--manifest",
                str(paths["releaseManifest"]),
            ],
        ),
        _command(
            "run-release-gate",
            "Run the hard release gate with full artifact evidence.",
            [
                ".\\.venv\\Scripts\\python.exe",
                "scripts\\release_gate.py",
                "--manifest",
                str(paths["releaseManifest"]),
            ],
            output=paths["releaseGate"],
        ),
    ]


def _command(command_id: str, description: str, argv: list[str], *, output: Path | None = None) -> dict[str, Any]:
    payload = {
        "id": command_id,
        "description": description,
        "argv": argv,
        "powershell": _powershell(argv, output),
    }
    if output is not None:
        payload["output"] = str(output)
    return payload


def _powershell(argv: list[str], output: Path | None) -> str:
    command = " ".join(_quote(value) for value in argv)
    return f"{command} > {_quote(str(output))}" if output else command


def _quote(value: str) -> str:
    if not value or any(character.isspace() for character in value) or any(character in value for character in "'`$"):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return value


def _markdown(runbook: dict[str, Any]) -> str:
    lines = [
        f"# FreeMail Controlled-Domain Runbook - {runbook['domain']}",
        "",
        f"- Generated: `{runbook['generatedAt']}`",
        f"- Boundary: `{runbook['vpnBoundary']}`",
        f"- Credential-free: `{str(runbook['credentialFree']).lower()}`",
        "",
        "## Commands",
        "",
    ]
    for command in runbook["commands"]:
        lines.extend(
            [
                f"### {command['id']}",
                "",
                command["description"],
                "",
                "```powershell",
                command["powershell"],
                "```",
                "",
            ]
        )
    lines.extend(["## Manual Inputs", ""])
    lines.extend(f"- {item}" for item in runbook["remainingManualInputs"])
    lines.append("")
    return "\n".join(lines)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any], *, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to overwrite")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, payload: str, *, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to overwrite")
    path.write_text(payload, encoding="utf-8")
