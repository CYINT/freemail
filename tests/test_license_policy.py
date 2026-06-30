import json

from scripts import qa_license_policy


def test_license_policy_rejects_denied_license():
    failures = qa_license_policy._check_license("bad-package", "Elastic License 2.0")

    assert failures == ["bad-package uses denied license metadata: Elastic License 2.0"]


def test_license_policy_accepts_allowed_expression():
    assert qa_license_policy._check_license("cryptography", "Apache-2.0 OR BSD-3-Clause") == []


def test_license_policy_requires_third_party_notice():
    failures = qa_license_policy._check_notice("httpx", "## Runtime Components\nFastAPI\n")

    assert failures == ["httpx is missing from THIRD_PARTY_NOTICES.md"]


def test_mobile_dependency_policy_reads_lockfile_license(tmp_path):
    mobile = tmp_path / "apps" / "mobile"
    mobile.mkdir(parents=True)
    (mobile / "package.json").write_text(
        json.dumps({"dependencies": {"react": "19.2.7", "bad": "1.0.0"}}),
        encoding="utf-8",
    )
    (mobile / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/react": {"license": "MIT"},
                    "node_modules/bad": {"license": "SSPL-1.0"},
                }
            }
        ),
        encoding="utf-8",
    )

    failures = qa_license_policy._check_mobile_dependencies(tmp_path, "react")

    assert "bad uses denied license metadata: SSPL-1.0" in failures
    assert "bad is missing from THIRD_PARTY_NOTICES.md" in failures
