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
        "eas.json": mobile / "eas.json",
        "App.tsx": mobile / "App.tsx",
        "src/api.ts": mobile / "src" / "api.ts",
        "src/offlineCache.ts": mobile / "src" / "offlineCache.ts",
        "src/sessionStore.ts": mobile / "src" / "sessionStore.ts",
        "iOS workflow": root / ".github" / "workflows" / "mobile-ios-native.yml",
    }
    failures = [f"missing mobile file: {name}" for name, path in files.items() if not path.is_file()]
    if failures:
        return failures

    package = json.loads(files["package.json"].read_text(encoding="utf-8"))
    app_config = json.loads(files["app.json"].read_text(encoding="utf-8"))
    eas_config = json.loads(files["eas.json"].read_text(encoding="utf-8"))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files.values())

    if package.get("license") != "AGPL-3.0-or-later":
        failures.append("mobile package must declare AGPL-3.0-or-later")
    scripts = package.get("scripts", {})
    if scripts.get("config:check") != "expo config --type public":
        failures.append("mobile package must expose config:check for Expo config validation")
    if scripts.get("native:prebuild:check") != "python ../../scripts/qa_mobile_native_prebuild.py":
        failures.append("mobile package must expose native:prebuild:check for native prebuild validation")
    dependencies = package.get("dependencies", {})
    for dependency in ["expo", "react-native", "expo-secure-store", "expo-document-picker", "expo-file-system", "expo-sharing"]:
        if dependency not in dependencies:
            failures.append(f"missing mobile dependency: {dependency}")
    expo_config = app_config.get("expo", {})
    if expo_config.get("extra", {}).get("apiBaseUrl") != "https://freemail.kuzuryu.ai":
        failures.append("mobile app must default to the VPN hostname")
    if expo_config.get("ios", {}).get("bundleIdentifier") != "technology.cyint.freemail":
        failures.append("mobile iOS bundle identifier must be technology.cyint.freemail")
    if expo_config.get("android", {}).get("package") != "technology.cyint.freemail":
        failures.append("mobile Android package must be technology.cyint.freemail")
    failures.extend(validate_eas_config(eas_config))

    for marker in [
        "/api/v1/mailbox/session",
        "/api/v1/mailbox/sessions",
        "/api/v1/mailbox/snapshot",
        "/api/v1/mailbox/search",
        "/api/v1/mailbox/thread",
        "offset=",
        "nextOffset",
        "hasMore",
        "Load more",
        "loadMoreMessages",
        "threadId",
        "threadSubject",
        "threadHint",
        "Thread:",
        "loadMailboxThread",
        "loadSelectedThread",
        "Conversation",
        "/api/v1/mailbox/contacts",
        "/api/v1/mailbox/saved-contacts",
        "/api/v1/mailbox/sender-rules",
        "/api/v1/mailbox/sender-rules/apply",
        "/api/v1/mailbox/recipient-rules",
        "/api/v1/mailbox/folder",
        "/api/v1/mailbox/folder/empty",
        "/api/v1/mailbox/push/devices",
        "/api/v1/mailbox/push/notifications",
        "/api/v1/mailbox/message",
        "/api/v1/mailbox/message/headers",
        "/api/v1/mailbox/message/attachment",
        "/api/v1/mailbox/message/source",
        "/api/v1/mailbox/message/import",
        "/api/v1/mailbox/message/archive",
        "/api/v1/mailbox/message/move",
        "/api/v1/mailbox/message/read-state",
        "/api/v1/mailbox/message/star-state",
        "/api/v1/mailbox/message/bulk",
        "/api/v1/mailbox/preferences",
        "/api/v1/mailbox/send",
        "/api/v1/mailbox/draft",
        "MailboxPreferences",
        "loadMailboxPreferences",
        "updateMailboxPreferences",
        "Save preferences",
        "Preferences saved",
        "MailboxSessionSummary",
        "loadMailboxSessions",
        "revokeMailboxSessionById",
        "revokeAllMailboxSessions",
        "Sign out everywhere",
        "withSignature",
        "SentMessage",
        "DraftMessage",
        "sentFolderSaved",
        "Sent Items was not updated",
        "saveMailboxDraft",
        "Save draft",
        "Draft saved",
        "Edit draft",
        "Draft loaded into compose",
        "editSelectedDraft",
        "isDraftMessage",
        "DocumentPicker.getDocumentAsync",
        "FileSystem.readAsStringAsync",
        "contentBase64",
        "Add attachments",
        "Remove",
        "loadMailboxContacts",
        "loadSavedMailboxContacts",
        "saveMailboxContact",
        "deleteMailboxContact",
        "Save contact",
        "MailboxSenderRule",
        "loadMailboxSenderRules",
        "saveMailboxSenderRule",
        "deleteMailboxSenderRule",
        "applyMailboxSenderRules",
        "MailboxRecipientRule",
        "loadMailboxRecipientRules",
        "saveMailboxRecipientRule",
        "deleteMailboxRecipientRule",
        "Save sender rule",
        "Save recipient rule",
        "saveSelectedSenderRule",
        "senderEmailFromText",
        "Allow sender",
        "Block sender",
        "Apply blocks",
        "searchMailbox",
        "createMailboxFolder",
        "renameMailboxFolder",
        "emptyMailboxFolder",
        "deleteMailboxFolder",
        "loadMailboxAttachment",
        "loadMailboxMessageHeaders",
        "headerSummary",
        "Headers",
        "loadMailboxMessageSource",
        "importMailboxMessageSource",
        "Export EML",
        "Import EML",
        "message/rfc822",
        "archiveMailboxMessage",
        "moveMailboxMessage",
        "setMailboxMessageReadState",
        "setMailboxMessageStarState",
        "bulkMailboxMessageAction",
        "selectedMessageIds",
        "bulkAction",
        "Messages archived",
        "Sharing.shareAsync",
        "FileSystem.writeAsStringAsync",
        "FileSystem.cacheDirectory",
        "Download",
        "Attachment downloaded to app cache",
        "Attachment ready to save",
        "registerMailboxPushDevice",
        "loadMailboxPushDevices",
        "revokeMailboxPushDevice",
        "createMailboxPushNotification",
        "loadMailboxPushNotifications",
        "getOrCreateMailboxDeviceRegistration",
        "Use this device",
        "development provider",
        "Push devices",
        "Register push device",
        "Send push test",
        "Push delivery test",
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
        "Ionicons",
        "Mobile shell navigation",
        "activeMobileTab",
        "mobileTabs",
        "accessibilityRole=\"tab\"",
        "Reply",
        "Forward",
        "Mark read",
        "Mark unread",
        "Message marked read",
        "Message marked unread",
        "Star",
        "Unstar",
        "Message starred",
        "Message unstarred",
        "Archive",
        "Spam",
        "Delete",
        "Message archived",
        "Message moved to spam",
        "Message deleted",
        "Contacts",
        "Folders",
        "https://freemail.kuzuryu.ai",
        "docs/mobile-release.md",
        "Mobile Release",
        "Native Build Drill",
        "Signing Material",
        "npm run config:check",
        "native:prebuild:check",
        "expo config --type public",
        "technology.cyint.freemail",
        "npx expo prebuild --clean --no-install --platform all",
        "Mobile iOS Native Drill",
        "eas.json",
        "private-beta",
        "distribution",
        "internal",
        "app-bundle",
        "EXPO_PUBLIC_FREEMAIL_API_BASE_URL",
        "macos-15",
        "scripts/qa_mobile_native_prebuild.py --link-node-modules --platform ios",
        "scripts/mobile_release_gate.py",
        "scripts\\collect_mobile_build_evidence.py",
        "scripts\\collect_mobile_device_validation.py",
        "scripts\\collect_mobile_store_submission.py",
        "mobile signed-build, store-submission, and real-device validation evidence",
        "--require-store-submission",
        "--artifact-sha256",
        "--all-checks-passed",
        "--review-state",
        "storeSubmissions",
        "deviceValidation",
        "privateBetaBoundary",
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


def validate_eas_config(eas_config: dict[str, object]) -> list[str]:
    failures = []
    cli = as_mapping(eas_config.get("cli"))
    if cli.get("appVersionSource") != "local":
        failures.append("mobile EAS config must use local app version source")
    if not str(cli.get("version") or "").startswith(">="):
        failures.append("mobile EAS config must pin a minimum EAS CLI version")

    build = as_mapping(eas_config.get("build"))
    for profile_name in ["development", "private-beta", "production"]:
        profile = as_mapping(build.get(profile_name))
        env = as_mapping(profile.get("env"))
        if env.get("EXPO_PUBLIC_FREEMAIL_API_BASE_URL") != "https://freemail.kuzuryu.ai":
            failures.append(f"mobile EAS {profile_name} profile must target the VPN hostname")
    private_beta = as_mapping(build.get("private-beta"))
    if private_beta.get("distribution") != "internal":
        failures.append("mobile EAS private-beta profile must use internal distribution")
    if as_mapping(private_beta.get("android")).get("buildType") != "app-bundle":
        failures.append("mobile EAS private-beta Android build must produce an app bundle")
    if as_mapping(private_beta.get("ios")).get("simulator") is not False:
        failures.append("mobile EAS private-beta iOS build must target physical devices")

    submit = as_mapping(eas_config.get("submit"))
    for profile_name in ["private-beta", "production"]:
        if profile_name not in submit:
            failures.append(f"mobile EAS submit profile missing: {profile_name}")

    serialized = json.dumps(eas_config).lower()
    for forbidden in [
        "apikey",
        "api_key",
        "certificate",
        "keystore",
        "password",
        "privatekey",
        "private_key",
        "provisioning",
        "token",
    ]:
        if forbidden in serialized:
            failures.append(f"mobile EAS config must not contain signing or secret material: {forbidden}")
    return failures


def as_mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    sys.exit(main())
