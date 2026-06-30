from pathlib import Path
import json
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures = validate_mobile(root)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("static mobile QA passed")
    return 0


def validate_mobile(root: Path) -> list[str]:
    mobile = root / "apps" / "mobile"
    files = {
        "docs/mobile-release.md": root / "docs" / "mobile-release.md",
        "README.md": mobile / "README.md",
        "package.json": mobile / "package.json",
        "app.json": mobile / "app.json",
        "App.tsx": mobile / "App.tsx",
        "src/api.ts": mobile / "src" / "api.ts",
        "src/offlineCache.ts": mobile / "src" / "offlineCache.ts",
        "src/sessionStore.ts": mobile / "src" / "sessionStore.ts",
    }
    failures = [f"missing mobile file: {name}" for name, path in files.items() if not path.is_file()]
    if failures:
        return failures

    package = json.loads(files["package.json"].read_text(encoding="utf-8"))
    app_config = json.loads(files["app.json"].read_text(encoding="utf-8"))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files.values())

    if package.get("license") != "AGPL-3.0-or-later":
        failures.append("mobile package must declare AGPL-3.0-or-later")
    scripts = package.get("scripts", {})
    if scripts.get("config:check") != "expo config --type public":
        failures.append("mobile package must expose config:check for Expo config validation")
    dependencies = package.get("dependencies", {})
    for dependency in ["expo", "react-native", "expo-secure-store", "expo-document-picker", "expo-file-system"]:
        if dependency not in dependencies:
            failures.append(f"missing mobile dependency: {dependency}")
    expo_config = app_config.get("expo", {})
    if expo_config.get("extra", {}).get("apiBaseUrl") != "https://freemail.kuzuryu.ai":
        failures.append("mobile app must default to the VPN hostname")
    if expo_config.get("ios", {}).get("bundleIdentifier") != "technology.cyint.freemail":
        failures.append("mobile iOS bundle identifier must be technology.cyint.freemail")
    if expo_config.get("android", {}).get("package") != "technology.cyint.freemail":
        failures.append("mobile Android package must be technology.cyint.freemail")

    for marker in [
        "/api/v1/mailbox/session",
        "/api/v1/mailbox/snapshot",
        "/api/v1/mailbox/search",
        "/api/v1/mailbox/contacts",
        "/api/v1/mailbox/folder",
        "/api/v1/mailbox/push/devices",
        "/api/v1/mailbox/message",
        "/api/v1/mailbox/message/attachment",
        "/api/v1/mailbox/send",
        "DocumentPicker.getDocumentAsync",
        "FileSystem.readAsStringAsync",
        "contentBase64",
        "Add attachments",
        "Remove",
        "loadMailboxContacts",
        "searchMailbox",
        "createMailboxFolder",
        "renameMailboxFolder",
        "deleteMailboxFolder",
        "loadMailboxAttachment",
        "registerMailboxPushDevice",
        "loadMailboxPushDevices",
        "revokeMailboxPushDevice",
        "Push devices",
        "Register push device",
        "saveCachedMailboxSnapshot",
        "loadCachedMailboxSnapshot",
        "clearCachedMailboxSnapshots",
        "freemail.mobile.offlineCache",
        "Showing cached",
        "Authorization",
        "Bearer",
        "SecureStore.setItemAsync",
        "SecureStore.getItemAsync",
        "SecureStore.deleteItemAsync",
        "WHEN_UNLOCKED_THIS_DEVICE_ONLY",
        "VPN-only mobile client",
        "Reply",
        "Forward",
        "Contacts",
        "Folders",
        "https://freemail.kuzuryu.ai",
        "docs/mobile-release.md",
        "Mobile Release",
        "Native Build Drill",
        "Signing Material",
        "npm run config:check",
        "expo config --type public",
        "technology.cyint.freemail",
        "npx expo prebuild --clean --no-install",
    ]:
        if marker not in combined:
            failures.append(f"missing mobile marker: {marker}")

    if (mobile / "ios").exists() or (mobile / "android").exists():
        failures.append("generated mobile native project directories must not be committed yet")
    for pattern in ["*.mobileprovision", "*.p12", "*.keystore", "*.jks"]:
        for forbidden_file in mobile.glob(pattern):
            failures.append(f"mobile signing material must not be committed: {forbidden_file.relative_to(root)}")

    for marker in ["Gmail", "Google", "AsyncStorage", "localStorage", "sessionStorage", "document.cookie"]:
        if marker.lower() in combined.lower():
            failures.append(f"forbidden mobile marker found: {marker}")
    if "password" in files["src/sessionStore.ts"].read_text(encoding="utf-8").lower():
        failures.append("mobile session store must not persist mailbox passwords")
    offline_cache = files["src/offlineCache.ts"].read_text(encoding="utf-8").lower()
    for marker in ["password", "token", "authorization", "bearer"]:
        if marker in offline_cache:
            failures.append(f"mobile offline cache must not persist credential marker: {marker}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
