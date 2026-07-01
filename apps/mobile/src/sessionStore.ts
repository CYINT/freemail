import * as SecureStore from "expo-secure-store";

import type { MailboxSession } from "./api";

const sessionKey = "freemail.mobile.mailboxSession";
const deviceRegistrationKey = "freemail.mobile.deviceRegistration";

export type MobileDeviceRegistration = {
  deviceId: string;
  developmentPushToken: string;
};

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

export async function getOrCreateMailboxDeviceRegistration(): Promise<MobileDeviceRegistration> {
  const stored = await loadMailboxDeviceRegistration();
  if (stored) {
    return stored;
  }
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  const registration = {
    deviceId: `freemail-${suffix}`,
    developmentPushToken: `development-${suffix}`,
  };
  await SecureStore.setItemAsync(deviceRegistrationKey, JSON.stringify(registration), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  return registration;
}

async function loadMailboxDeviceRegistration(): Promise<MobileDeviceRegistration | null> {
  const raw = await SecureStore.getItemAsync(deviceRegistrationKey);
  if (!raw) {
    return null;
  }
  const parsed = JSON.parse(raw);
  if (!parsed?.deviceId || !parsed?.developmentPushToken) {
    return null;
  }
  return {
    deviceId: String(parsed.deviceId),
    developmentPushToken: String(parsed.developmentPushToken),
  };
}
