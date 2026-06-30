from pathlib import Path

from scripts import qa_mobile_native_prebuild


def test_validate_no_generated_native_projects_blocks_committed_outputs(tmp_path):
    mobile = tmp_path / "apps" / "mobile"
    (mobile / "ios").mkdir(parents=True)
    (mobile / "release.keystore").write_text("secret", encoding="utf-8")

    failures = qa_mobile_native_prebuild.validate_no_generated_native_projects(tmp_path)

    assert "generated native directory must not be committed: apps/mobile/ios" in failures
    assert any("release.keystore" in failure for failure in failures)


def test_validate_generated_android_project_accepts_debug_keystore(tmp_path):
    mobile = tmp_path
    write(mobile / "app.json", '"https://freemail.kuzuryu.ai"')
    write(mobile / "android" / "settings.gradle", "pluginManagement {}")
    write(mobile / "android" / "app" / "build.gradle", 'namespace "technology.cyint.freemail"')
    write(mobile / "android" / "app" / "src" / "main" / "AndroidManifest.xml", "technology.cyint.freemail")
    write(mobile / "android" / "app" / "debug.keystore", "generated debug key")

    failures = qa_mobile_native_prebuild.validate_generated_native_projects(mobile, platform="android")

    assert failures == []


def test_validate_generated_ios_project_requires_bundle_identifier(tmp_path):
    mobile = tmp_path
    write(mobile / "app.json", '"https://freemail.kuzuryu.ai"')
    write(mobile / "ios" / "Podfile", "target 'FreeMail'")
    write(mobile / "ios" / "FreeMail.xcodeproj" / "project.pbxproj", "PRODUCT_BUNDLE_IDENTIFIER = wrong;")

    failures = qa_mobile_native_prebuild.validate_generated_native_projects(mobile, platform="ios")

    assert failures == ["native iOS project must use bundle identifier technology.cyint.freemail"]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
