from pathlib import Path
import subprocess
import sys

from scripts.qa_mobile_static import validate_eas_config, validate_mobile


def test_mobile_static_contract_passes():
    root = Path(__file__).resolve().parents[1]

    assert validate_mobile(root) == []


def test_mobile_static_script_passes():
    result = subprocess.run(
        [sys.executable, "scripts/qa_mobile_static.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_mobile_static_validation_flags_bad_eas_private_beta_profile():
    failures = validate_eas_config(
        {
            "cli": {"appVersionSource": "remote", "version": "16.0.0"},
            "build": {
                "development": {"env": {"EXPO_PUBLIC_FREEMAIL_API_BASE_URL": "https://freemail.kuzuryu.ai"}},
                "private-beta": {
                    "distribution": "store",
                    "env": {"EXPO_PUBLIC_FREEMAIL_API_BASE_URL": "https://public.example.invalid"},
                    "ios": {"simulator": True},
                    "android": {"buildType": "apk"},
                },
                "production": {"env": {"EXPO_PUBLIC_FREEMAIL_API_BASE_URL": "https://freemail.kuzuryu.ai"}},
            },
            "submit": {},
        }
    )

    assert "mobile EAS config must use local app version source" in failures
    assert "mobile EAS config must pin a minimum EAS CLI version" in failures
    assert "mobile EAS private-beta profile must target the VPN hostname" in failures
    assert "mobile EAS private-beta profile must use internal distribution" in failures
    assert "mobile EAS private-beta Android build must produce an app bundle" in failures
    assert "mobile EAS private-beta iOS build must target physical devices" in failures
