import * as SecureStore from "expo-secure-store";

import type { MailboxSession, MailboxSnapshot, MailContact } from "./api";

const cacheIndexPrefix = "freemail.mobile.offlineCache.index";
const cacheEntryPrefix = "freemail.mobile.offlineCache.snapshot";

export type CachedMailboxSnapshot = {
  cachedAt: string;
  email: string;
  folder: string;
  folders: MailboxSnapshot["folders"];
  messages: MailboxSnapshot["messages"];
  contacts: MailContact[];
};

export async function saveCachedMailboxSnapshot(
  session: MailboxSession,
  folder: string,
  snapshot: MailboxSnapshot,
  contacts: MailContact[],
): Promise<void> {
  const normalizedFolder = normalizeFolder(folder);
  const cached: CachedMailboxSnapshot = {
    cachedAt: new Date().toISOString(),
    email: session.email,
    folder: normalizedFolder,
    folders: snapshot.folders || [],
    messages: snapshot.messages || [],
    contacts,
  };
  await SecureStore.setItemAsync(cacheEntryKey(session.email, normalizedFolder), JSON.stringify(cached), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  await rememberCachedFolder(session.email, normalizedFolder);
}

export async function loadCachedMailboxSnapshot(
  session: MailboxSession,
  folder: string,
): Promise<CachedMailboxSnapshot | null> {
  const raw = await SecureStore.getItemAsync(cacheEntryKey(session.email, normalizeFolder(folder)));
  if (!raw) {
    return null;
  }
  const parsed = JSON.parse(raw);
  if (!parsed?.email || !parsed?.folder || !Array.isArray(parsed?.messages)) {
    return null;
  }
  return {
    cachedAt: String(parsed.cachedAt || ""),
    email: String(parsed.email),
    folder: String(parsed.folder),
    folders: Array.isArray(parsed.folders) ? parsed.folders : [],
    messages: parsed.messages,
    contacts: Array.isArray(parsed.contacts) ? parsed.contacts : [],
  };
}

export async function clearCachedMailboxSnapshots(email: string): Promise<void> {
  const folders = await loadCachedFolderIndex(email);
  await Promise.all(folders.map((folder) => SecureStore.deleteItemAsync(cacheEntryKey(email, folder))));
  await SecureStore.deleteItemAsync(cacheIndexKey(email));
}

async function rememberCachedFolder(email: string, folder: string): Promise<void> {
  const folders = new Set(await loadCachedFolderIndex(email));
  folders.add(folder);
  await SecureStore.setItemAsync(cacheIndexKey(email), JSON.stringify([...folders].sort()), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

async function loadCachedFolderIndex(email: string): Promise<string[]> {
  const raw = await SecureStore.getItemAsync(cacheIndexKey(email));
  if (!raw) {
    return [];
  }
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed.map(String) : [];
}

function cacheIndexKey(email: string): string {
  return `${cacheIndexPrefix}.${encodeKeyPart(email)}`;
}

function cacheEntryKey(email: string, folder: string): string {
  return `${cacheEntryPrefix}.${encodeKeyPart(email)}.${encodeKeyPart(folder)}`;
}

function normalizeFolder(folder: string): string {
  return folder.trim() || "INBOX";
}

function encodeKeyPart(value: string): string {
  return encodeURIComponent(value.toLowerCase());
}
