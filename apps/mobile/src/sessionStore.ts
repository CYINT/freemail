import * as SecureStore from "expo-secure-store";

import type { MailboxSession } from "./api";

const sessionKey = "freemail.mobile.mailboxSession";

export async function saveMailboxSession(session: MailboxSession): Promise<void> {
  await SecureStore.setItemAsync(sessionKey, JSON.stringify(session), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

export async function loadStoredMailboxSession(): Promise<MailboxSession | null> {
  const raw = await SecureStore.getItemAsync(sessionKey);
  if (!raw) {
    return null;
  }
  const parsed = JSON.parse(raw);
  if (!parsed?.token || !parsed?.apiBaseUrl || !parsed?.email) {
    return null;
  }
  return {
    email: String(parsed.email),
    token: String(parsed.token),
    apiBaseUrl: String(parsed.apiBaseUrl),
  };
}

export async function clearStoredMailboxSession(): Promise<void> {
  await SecureStore.deleteItemAsync(sessionKey);
}
