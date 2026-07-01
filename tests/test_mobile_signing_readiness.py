import subprocess

from scripts.mobile_signing_readiness import check_mobile_signing_readiness


def test_mobile_signing_readiness_reports_missing_expo_token(monkeypatch):
    def fake_run(command, check, capture_output, text):
        assert check is False
        assert capture_output is True
        assert text is True
        if command[1:3] == ["workflow", "list"]:
            return subprocess.CompletedProcess(command, 0, stdout="Mobile EAS Private Beta\tactive\t1\n")
        if command[1:3] == ["secret", "list"]:
            return subprocess.CompletedProcess(command, 0, stdout="CODECOV_TOKEN\t2026-06-30T03:24:45Z\n")
        raise AssertionError(command)

    monkeypatch.setattr("scripts.mobile_signing_readiness.subprocess.run", fake_run)

    result = check_mobile_signing_readiness(repo="CYINT/freemail")

    assert result["ready"] is False
    assert result["workflowPresent"] is True
    assert result["configuredRequiredSecrets"] == []
    assert result["missingSecrets"] == ["EXPO_TOKEN"]
    assert result["credentialFree"] is True
    assert result["nextActions"] == [
        {
            "id": "configure-expo-token",
            "reason": "EXPO_TOKEN GitHub Actions secret is required for signed EAS builds",
            "command": "gh secret set EXPO_TOKEN --repo CYINT/freemail",
        }
    ]


def test_mobile_signing_readiness_passes_with_workflow_and_secret(monkeypatch):
    def fake_run(command, check, capture_output, text):
        if command[1:3] == ["workflow", "list"]:
            return subprocess.CompletedProcess(command, 0, stdout="Mobile EAS Private Beta\tactive\t1\n")
        if command[1:3] == ["secret", "list"]:
            return subprocess.CompletedProcess(command, 0, stdout="EXPO_TOKEN\t2026-07-01T00:00:00Z\n")
        raise AssertionError(command)

    monkeypatch.setattr("scripts.mobile_signing_readiness.subprocess.run", fake_run)

    result = check_mobile_signing_readiness(repo="CYINT/freemail")

    assert result["ready"] is True
    assert result["missingSecrets"] == []
    assert result["configuredRequiredSecrets"] == ["EXPO_TOKEN"]
    assert result["nextActions"][0]["id"] == "run-mobile-eas-private-beta"
    assert "mobile-eas-private-beta.yml" in result["nextActions"][0]["command"]


def test_mobile_signing_readiness_reports_missing_workflow(monkeypatch):
    def fake_run(command, check, capture_output, text):
        if command[1:3] == ["workflow", "list"]:
            return subprocess.CompletedProcess(command, 0, stdout="CI\tactive\t1\n")
        if command[1:3] == ["secret", "list"]:
            return subprocess.CompletedProcess(command, 0, stdout="EXPO_TOKEN\t2026-07-01T00:00:00Z\n")
        raise AssertionError(command)

    monkeypatch.setattr("scripts.mobile_signing_readiness.subprocess.run", fake_run)

    result = check_mobile_signing_readiness(repo="CYINT/freemail")

    assert result["ready"] is False
    assert result["workflowPresent"] is False
    assert result["missingSecrets"] == []
    assert result["nextActions"][0]["id"] == "publish-mobile-eas-workflow"
