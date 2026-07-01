from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


IGNORED_APP_DIRS = {"node_modules", "ios", "android", ".expo", "dist", "build"}
FORBIDDEN_SIGNING_GLOBS = ("*.mobileprovision", "*.p12", "*.keystore", "*.jks")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the FreeMail mobile native prebuild drill in a temp copy.")
    parser.add_argument(
        "--link-node-modules",
        action="store_true",
        help="Symlink apps/mobile/node_modules into the temp copy instead of running npm ci.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep the temporary prebuild directory for manual inspection.",
    )
    parser.add_argument(
        "--platform",
        choices=("android", "ios", "all"),
        default="android",
        help="Native platform to prebuild and validate. Use all only on hosts that support iOS generation.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    failures = validate_no_generated_native_projects(root)
    if failures:
        return report_failures(failures)

    temp_root = Path(tempfile.mkdtemp(prefix="freemail-mobile-prebuild-"))
    try:
        temp_mobile = temp_root / "mobile"
        copy_mobile_app(root / "apps" / "mobile", temp_mobile)
        prepare_dependencies(root / "apps" / "mobile", temp_mobile, args.link_node_modules)
        run(["npx", "expo", "prebuild", "--clean", "--no-install", "--platform", args.platform], cwd=temp_mobile)
        failures = validate_generated_native_projects(temp_mobile, platform=args.platform)
        if failures:
            return report_failures(failures)
        print(f"mobile native prebuild QA passed in {temp_mobile}")
        return 0
    finally:
        if args.keep_workdir:
            print(f"kept mobile native prebuild workdir: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


def copy_mobile_app(source: Path, destination: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in IGNORED_APP_DIRS}

    shutil.copytree(source, destination, ignore=ignore)


def prepare_dependencies(source: Path, destination: Path, link_node_modules: bool) -> None:
    source_node_modules = source / "node_modules"
    destination_node_modules = destination / "node_modules"
    if link_node_modules and source_node_modules.is_dir():
        try:
            destination_node_modules.symlink_to(source_node_modules, target_is_directory=True)
            return
        except OSError as exc:
            print(f"node_modules symlink unavailable ({exc}); falling back to npm ci", file=sys.stderr)
    run(["npm", "ci"], cwd=destination)


def validate_no_generated_native_projects(root: Path) -> list[str]:
    mobile = root / "apps" / "mobile"
    failures = []
    for directory in ("ios", "android"):
        if (mobile / directory).exists():
            failures.append(f"generated native directory must not be committed: apps/mobile/{directory}")
    for pattern in FORBIDDEN_SIGNING_GLOBS:
        for path in mobile.rglob(pattern):
            failures.append(f"mobile signing material must not be committed: {path.relative_to(root)}")
    return failures


def validate_generated_native_projects(mobile: Path, *, platform: str) -> list[str]:
    required_files = []
    if platform in {"android", "all"}:
        required_files.extend(
            [
                mobile / "android" / "settings.gradle",
                mobile / "android" / "app" / "build.gradle",
                mobile / "android" / "app" / "src" / "main" / "AndroidManifest.xml",
            ]
        )
    if platform in {"ios", "all"}:
        required_files.append(mobile / "ios" / "Podfile")
    failures = [f"native prebuild did not generate {path.relative_to(mobile)}" for path in required_files if not path.is_file()]
    failures.extend(validate_generated_identifier(mobile, platform=platform))
    for pattern in FORBIDDEN_SIGNING_GLOBS:
        for path in mobile.rglob(pattern):
            if path.relative_to(mobile).as_posix() == "android/app/debug.keystore":
                continue
            failures.append(f"native prebuild generated forbidden signing material: {path.relative_to(mobile)}")
    return failures


def validate_generated_identifier(mobile: Path, *, platform: str) -> list[str]:
    failures = []
    android_manifest = mobile / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    android_build = mobile / "android" / "app" / "build.gradle"
    ios_project_files = list((mobile / "ios").glob("*.xcodeproj/project.pbxproj"))
    android_text = "\n".join(read_text(path) for path in (android_manifest, android_build))
    ios_text = "\n".join(read_text(path) for path in ios_project_files)
    if platform in {"android", "all"} and "technology.cyint.freemail" not in android_text:
        failures.append("native Android project must use package technology.cyint.freemail")
    if platform in {"ios", "all"} and "technology.cyint.freemail" not in ios_text:
        failures.append("native iOS project must use bundle identifier technology.cyint.freemail")
    if "https://freemail.kuzuryu.ai" not in read_text(mobile / "app.json"):
        failures.append("native prebuild source config must keep the VPN API target")
    return failures


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def run(command: list[str], *, cwd: Path) -> None:
    executable = shutil.which(command[0])
    if executable is None:
        raise FileNotFoundError(f"required command was not found on PATH: {command[0]}")
    subprocess.run([executable, *command[1:]], cwd=cwd, check=True)


def report_failures(failures: list[str]) -> int:
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
