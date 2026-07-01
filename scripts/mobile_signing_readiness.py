import argparse
import json
import subprocess
import sys


DEFAULT_REPO = "CYINT/freemail"
DEFAULT_WORKFLOW = "Mobile EAS Private Beta"
DEFAULT_REQUIRED_SECRETS = ("EXPO_TOKEN",)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check credential-free mobile signing workflow readiness.")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--required-secret", action="append", dest="required_secrets")
    args = parser.parse_args()

    result = check_mobile_signing_readiness(
        repo=args.repo,
        workflow=args.workflow,
        required_secrets=tuple(args.required_secrets or DEFAULT_REQUIRED_SECRETS),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready"] else 1


def check_mobile_signing_readiness(
    *,
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    required_secrets: tuple[str, ...] = DEFAULT_REQUIRED_SECRETS,
) -> dict[str, object]:
    workflow_result = _run_gh(["workflow", "list", "--repo", repo])
    secret_result = _run_gh(["secret", "list", "--repo", repo])
    workflow_names = _first_columns(workflow_result.stdout)
    secret_names = _first_columns(secret_result.stdout)
    missing_secrets = [secret for secret in required_secrets if secret not in secret_names]
    missing_workflow = workflow not in workflow_names
    command_failures = []
    if workflow_result.returncode != 0:
        command_failures.append("gh workflow list failed")
    if secret_result.returncode != 0:
        command_failures.append("gh secret list failed")

    ready = not missing_workflow and not missing_secrets and not command_failures
    return {
        "ready": ready,
        "repo": repo,
        "workflow": workflow,
        "workflowPresent": not missing_workflow,
        "requiredSecrets": list(required_secrets),
        "configuredRequiredSecrets": [secret for secret in required_secrets if secret in secret_names],
        "missingSecrets": missing_secrets,
        "credentialFree": True,
        "commandFailures": command_failures,
        "nextActions": _next_actions(repo=repo, workflow=workflow, missing_workflow=missing_workflow, missing_secrets=missing_secrets),
    }


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _first_columns(output: str) -> set[str]:
    names = set()
    for line in output.splitlines():
        parts = line.split("\t")
        if parts and parts[0].strip():
            names.add(parts[0].strip())
    return names


def _next_actions(*, repo: str, workflow: str, missing_workflow: bool, missing_secrets: list[str]) -> list[dict[str, object]]:
    actions = []
    if missing_workflow:
        actions.append(
            {
                "id": "publish-mobile-eas-workflow",
                "reason": f"{workflow} workflow is not registered in GitHub Actions",
                "command": f"git push origin main && gh workflow list --repo {repo}",
            }
        )
    for secret in missing_secrets:
        actions.append(
            {
                "id": f"configure-{secret.lower().replace('_', '-')}",
                "reason": f"{secret} GitHub Actions secret is required for signed EAS builds",
                "command": f"gh secret set {secret} --repo {repo}",
            }
        )
    if not actions:
        actions.append(
            {
                "id": "run-mobile-eas-private-beta",
                "reason": "mobile signing workflow and required secret names are configured",
                "command": f"gh workflow run mobile-eas-private-beta.yml --repo {repo} -f platform=<ios-or-android> -f profile=private-beta -f submit_after_build=false -f confirmation=launch-mobile-private-beta",
            }
        )
    return actions


if __name__ == "__main__":
    sys.exit(main())
