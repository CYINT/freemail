from pathlib import Path
import subprocess
import sys

from scripts.qa_mobile_static import validate_mobile


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
