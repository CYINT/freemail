export type MailboxSession = {
  email: string;
  token: string;
  apiBaseUrl: string;
};

export type PublicUserInvitation = {
  email: string;
  displayName: string;
  isAdmin: boolean;
  adminRole: string;
  expiresAt: number;
};

export type AcceptedUserInvitation = {
  email: string;
  displayName: string;
  isAdmin: boolean;
  adminRole: string;
};

export type MailboxSessionSummary = {
  id: number;
  email: string;
  expiresAt: number;
  createdAt: string;
  current: boolean;
};

export type MailboxSessions = {
  email: string;
  sessions: MailboxSessionSummary[];
};

export type MailFolder = {
  name: string;
  messageCount: number;
  unreadCount: number;
};

export type MailMessage = {
  folder: string;
  messageId: string;
  subject: string;
  sender: string;
  recipients: string;
  date: string;
  unread: boolean;
  starred: boolean;
  threadId: string;
  threadSubject: string;
  inReplyTo?: string | null;
};

export type MailAttachment = {
  attachmentId: string;
  filename: string;
  contentType: string;
  size: number;
};

export type MailMessageDetail = MailMessage & {
  body: string;
  attachments: MailAttachment[];
};

export type MailHeaderField = {
  name: string;
  value: string;
};

export type MailMessageHeaders = {
  folder: string;
  messageId: string;
  subject: string;
  sender: string;
  recipients: string;
  date: string;
  messageIdHeader: string;
  replyTo: string;
  authenticationResults: string[];
  listUnsubscribe: string;
  receivedCount: number;
  headers: MailHeaderField[];
};

export type MailboxSnapshot = {
  email: string;
  folders: MailFolder[];
  messages: MailMessage[];
  limit: number;
  offset: number;
  nextOffset: number | null;
  hasMore: boolean;
};

export type MailboxSearch = {
  email: string;
  folder: string;
  query: string;
  messages: MailMessage[];
  limit: number;
  offset: number;
  nextOffset: number | null;
  hasMore: boolean;
};

export type MailboxThread = {
  email: string;
  folder: string;
  threadId: string;
  threadSubject: string;
  messages: MailMessage[];
};

export type MailContact = {
  name: string;
  email: string;
  messageCount: number;
};

export type SavedMailContact = {
  id: number;
  mailboxEmail: string;
  contactEmail: string;
  displayName: string;
  notes: string;
  createdAt: string;
  updatedAt: string;
};

export type MailboxContacts = {
  email: string;
  folder: string;
  contacts: MailContact[];
};

export type SavedMailboxContacts = {
  mailboxEmail: string;
  contacts: SavedMailContact[];
};

export type MailboxSenderRule = {
  id: number;
  mailboxEmail: string;
  senderEmail: string;
  action: "allow" | "block";
  notes: string;
  createdAt: string;
  updatedAt: string;
};

export type MailboxSenderRules = {
  mailboxEmail: string;
  rules: MailboxSenderRule[];
};

export type MailboxRecipientRule = {
  id: number;
  mailboxEmail: string;
  recipientEmail: string;
  action: "allow" | "block";
  notes: string;
  createdAt: string;
  updatedAt: string;
};

export type MailboxRecipientRules = {
  mailboxEmail: string;
  rules: MailboxRecipientRule[];
};

export type AppliedSenderRules = {
  folder: string;
  targetFolder: string;
  blockedSenders: string[];
  allowedSenders: string[];
  messageIds: string[];
  moved: number;
};

export type MailboxPushDevice = {
  id: number;
  mailboxEmail: string;
  deviceId: string;
  platform: "ios" | "android" | "web" | "development";
  provider: string;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
};

export type MailboxPushNotification = {
  id: number;
  mailboxEmail: string;
  deviceId: string;
  provider: string;
  title: string;
  body: string;
  status: string;
  providerMessageId: string | null;
  lastError: string | null;
  createdAt: string;
  deliveredAt: string | null;
};

export type ComposeMessage = {
  recipients: string[];
  subject: string;
  body: string;
  attachments?: ComposeAttachment[];
};

export type ComposeAttachment = {
  filename: string;
  contentType: string;
  contentBase64: string;
};

export type SentMessage = {
  accepted: boolean;
  messageId: string;
  sender: string;
  recipients: string[];
  subject: string;
  sentFolder: string;
  sentFolderSaved: boolean;
};

export type DraftMessage = {
  saved: boolean;
  messageId: string;
  sender: string;
  recipients: string[];
  subject: string;
  draftFolder: string;
};

export type ImportedMessage = {
  folder: string;
  filename: string;
  size: number;
  imported: boolean;
};

export type BulkMessageAction = {
  folder: string;
  action: string;
  messageIds: string[];
  targetFolder?: string | null;
  succeeded: number;
};

export type MailboxPreferences = {
  mailboxEmail: string;
  displayName: string;
  signature: string;
  updatedAt: string;
};

export async function createMailboxSession(apiBaseUrl: string, email: string, password: string): Promise<MailboxSession> {
  const response = await request(apiBaseUrl, "/api/v1/mailbox/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const payload = await response.json();
  return {
    email: String(payload.email || email),
    token: String(payload.token),
    apiBaseUrl: normalizedApiBaseUrl(apiBaseUrl),
  };
}

export async function loadUserInvitation(apiBaseUrl: string, token: string): Promise<PublicUserInvitation> {
  const response = await request(apiBaseUrl, `/api/v1/invitations/${encodeURIComponent(token)}`, {
    method: "GET",
  });
  return response.json();
}

export async function acceptUserInvitation(
  apiBaseUrl: string,
  token: string,
  password: string,
  displayName = "",
): Promise<AcceptedUserInvitation> {
  const response = await request(apiBaseUrl, `/api/v1/invitations/${encodeURIComponent(token)}/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password, displayName }),
  });
  return response.json();
}

export async function revokeMailboxSession(session: MailboxSession): Promise<void> {
  await request(session.apiBaseUrl, "/api/v1/mailbox/session", {
    method: "DELETE",
    headers: mailboxHeaders(session),
  });
}

export async function loadMailboxSessions(session: MailboxSession): Promise<MailboxSessions> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/sessions", {
    headers: mailboxHeaders(session),
  });
  return response.json();
}

export async function revokeAllMailboxSessions(session: MailboxSession): Promise<number> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/sessions", {
    method: "DELETE",
    headers: mailboxHeaders(session),
  });
  const payload = await response.json();
  return Number(payload.revoked || 0);
}

export async function revokeMailboxSessionById(session: MailboxSession, sessionId: number): Promise<boolean> {
  const response = await request(session.apiBaseUrl, `/api/v1/mailbox/sessions/${sessionId}`, {
    method: "DELETE",
    headers: mailboxHeaders(session),
  });
  const payload = await response.json();
  return Boolean(payload.revoked);
}

export async function loadMailboxSnapshot(
  session: MailboxSession,
  folder = "INBOX",
  offset = 0,
  limit = 25,
): Promise<MailboxSnapshot> {
  const path = `/api/v1/mailbox/snapshot?folder=${encodeURIComponent(folder)}&limit=${limit}&offset=${offset}`;
  const response = await request(session.apiBaseUrl, path, { headers: mailboxHeaders(session) });
  return response.json();
}

export async function searchMailbox(
  session: MailboxSession,
  folder: string,
  query: string,
  offset = 0,
  limit = 25,
): Promise<MailboxSearch> {
  const path = `/api/v1/mailbox/search?folder=${encodeURIComponent(folder)}&query=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`;
  const response = await request(session.apiBaseUrl, path, { headers: mailboxHeaders(session) });
  return response.json();
}

export async function loadMailboxThread(
  session: MailboxSession,
  folder: string,
  threadId: string,
  limit = 100,
): Promise<MailboxThread> {
  const path = `/api/v1/mailbox/thread?folder=${encodeURIComponent(folder)}&thread_id=${encodeURIComponent(threadId)}&limit=${limit}`;
  const response = await request(session.apiBaseUrl, path, { headers: mailboxHeaders(session) });
  return response.json();
}

export async function loadMailboxContacts(session: MailboxSession, folder: string): Promise<MailboxContacts> {
  const path = `/api/v1/mailbox/contacts?folder=${encodeURIComponent(folder)}&limit=100`;
  const response = await request(session.apiBaseUrl, path, { headers: mailboxHeaders(session) });
  return response.json();
}

export async function loadSavedMailboxContacts(session: MailboxSession): Promise<SavedMailboxContacts> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/saved-contacts", {
    headers: mailboxHeaders(session),
  });
  return response.json();
}

export async function saveMailboxContact(
  session: MailboxSession,
  email: string,
  displayName = "",
  notes = "",
): Promise<SavedMailContact> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/saved-contacts", {
    method: "PUT",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, displayName, notes }),
  });
  return response.json();
}

export async function deleteMailboxContact(session: MailboxSession, contactId: number): Promise<void> {
  await request(session.apiBaseUrl, `/api/v1/mailbox/saved-contacts/${contactId}`, {
    method: "DELETE",
    headers: mailboxHeaders(session),
  });
}

export async function loadMailboxSenderRules(session: MailboxSession): Promise<MailboxSenderRules> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/sender-rules", {
    headers: mailboxHeaders(session),
  });
  return response.json();
}

export async function saveMailboxSenderRule(
  session: MailboxSession,
  senderEmail: string,
  action: "allow" | "block",
  notes = "",
): Promise<MailboxSenderRule> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/sender-rules", {
    method: "PUT",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ senderEmail, action, notes }),
  });
  return response.json();
}

export async function deleteMailboxSenderRule(session: MailboxSession, ruleId: number): Promise<void> {
  await request(session.apiBaseUrl, `/api/v1/mailbox/sender-rules/${ruleId}`, {
    method: "DELETE",
    headers: mailboxHeaders(session),
  });
}

export async function applyMailboxSenderRules(
  session: MailboxSession,
  folder: string,
  targetFolder = "Junk Mail",
): Promise<AppliedSenderRules> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/sender-rules/apply", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder, targetFolder }),
  });
  return response.json();
}

export async function loadMailboxRecipientRules(session: MailboxSession): Promise<MailboxRecipientRules> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/recipient-rules", {
    headers: mailboxHeaders(session),
  });
  return response.json();
}

export async function saveMailboxRecipientRule(
  session: MailboxSession,
  recipientEmail: string,
  action: "allow" | "block",
  notes = "",
): Promise<MailboxRecipientRule> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/recipient-rules", {
    method: "PUT",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ recipientEmail, action, notes }),
  });
  return response.json();
}

export async function deleteMailboxRecipientRule(session: MailboxSession, ruleId: number): Promise<void> {
  await request(session.apiBaseUrl, `/api/v1/mailbox/recipient-rules/${ruleId}`, {
    method: "DELETE",
    headers: mailboxHeaders(session),
  });
}

export async function loadMailboxMessage(
  session: MailboxSession,
  folder: string,
  messageId: string,
): Promise<MailMessageDetail> {
  const path = `/api/v1/mailbox/message?folder=${encodeURIComponent(folder)}&message_id=${encodeURIComponent(messageId)}`;
  const response = await request(session.apiBaseUrl, path, { headers: mailboxHeaders(session) });
  return response.json();
}

export async function loadMailboxMessageHeaders(
  session: MailboxSession,
  folder: string,
  messageId: string,
): Promise<MailMessageHeaders> {
  const path = `/api/v1/mailbox/message/headers?folder=${encodeURIComponent(folder)}&message_id=${encodeURIComponent(messageId)}`;
  const response = await request(session.apiBaseUrl, path, { headers: mailboxHeaders(session) });
  return response.json();
}

export async function loadMailboxAttachment(
  session: MailboxSession,
  folder: string,
  messageId: string,
  attachmentId: string,
): Promise<Blob> {
  const path =
    `/api/v1/mailbox/message/attachment?folder=${encodeURIComponent(folder)}` +
    `&message_id=${encodeURIComponent(messageId)}&attachment_id=${encodeURIComponent(attachmentId)}`;
  const response = await request(session.apiBaseUrl, path, { headers: mailboxHeaders(session) });
  return response.blob();
}

export async function loadMailboxMessageSource(
  session: MailboxSession,
  folder: string,
  messageId: string,
): Promise<Blob> {
  const path =
    `/api/v1/mailbox/message/source?folder=${encodeURIComponent(folder)}` +
    `&message_id=${encodeURIComponent(messageId)}`;
  const response = await request(session.apiBaseUrl, path, { headers: mailboxHeaders(session) });
  return response.blob();
}

export async function importMailboxMessageSource(
  session: MailboxSession,
  folder: string,
  filename: string,
  contentBase64: string,
): Promise<ImportedMessage> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/message/import", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder, filename, contentBase64 }),
  });
  return response.json();
}

export async function archiveMailboxMessage(
  session: MailboxSession,
  folder: string,
  messageId: string,
  archiveFolder = "Archive",
): Promise<void> {
  await request(session.apiBaseUrl, "/api/v1/mailbox/message/archive", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder, messageId, archiveFolder }),
  });
}

export async function moveMailboxMessage(
  session: MailboxSession,
  folder: string,
  messageId: string,
  targetFolder: string,
): Promise<void> {
  await request(session.apiBaseUrl, "/api/v1/mailbox/message/move", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder, messageId, targetFolder }),
  });
}

export async function setMailboxMessageReadState(
  session: MailboxSession,
  folder: string,
  messageId: string,
  read: boolean,
): Promise<void> {
  await request(session.apiBaseUrl, "/api/v1/mailbox/message/read-state", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder, messageId, read }),
  });
}

export async function setMailboxMessageStarState(
  session: MailboxSession,
  folder: string,
  messageId: string,
  starred: boolean,
): Promise<void> {
  await request(session.apiBaseUrl, "/api/v1/mailbox/message/star-state", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder, messageId, starred }),
  });
}

export async function bulkMailboxMessageAction(
  session: MailboxSession,
  folder: string,
  messageIds: string[],
  action: "read" | "unread" | "star" | "unstar" | "archive" | "spam" | "delete" | "move",
  targetFolder?: string,
): Promise<BulkMessageAction> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/message/bulk", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder, messageIds, action, targetFolder }),
  });
  return response.json();
}

export async function registerMailboxPushDevice(
  session: MailboxSession,
  deviceId: string,
  pushToken: string,
  provider = "contract-only",
): Promise<MailboxPushDevice> {
  const platform = devicePlatform();
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/push/devices", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ deviceId, platform, pushToken, provider }),
  });
  return response.json();
}

export async function loadMailboxPushDevices(session: MailboxSession): Promise<MailboxPushDevice[]> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/push/devices", {
    headers: mailboxHeaders(session),
  });
  return response.json();
}

export async function revokeMailboxPushDevice(session: MailboxSession, deviceId: string): Promise<void> {
  await request(session.apiBaseUrl, `/api/v1/mailbox/push/devices/${encodeURIComponent(deviceId)}`, {
    method: "DELETE",
    headers: mailboxHeaders(session),
  });
}

export async function createMailboxPushNotification(
  session: MailboxSession,
  title: string,
  body: string,
): Promise<MailboxPushNotification[]> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/push/notifications", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title, body }),
  });
  return response.json();
}

export async function loadMailboxPushNotifications(session: MailboxSession): Promise<MailboxPushNotification[]> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/push/notifications?limit=10", {
    headers: mailboxHeaders(session),
  });
  return response.json();
}

export async function sendMailboxMessage(session: MailboxSession, message: ComposeMessage): Promise<SentMessage> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/send", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(message),
  });
  return response.json();
}

export async function saveMailboxDraft(session: MailboxSession, message: ComposeMessage): Promise<DraftMessage> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/draft", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ...message, draftFolder: "Drafts" }),
  });
  return response.json();
}

export async function loadMailboxPreferences(session: MailboxSession): Promise<MailboxPreferences> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/preferences", {
    headers: mailboxHeaders(session),
  });
  return response.json();
}

export async function updateMailboxPreferences(
  session: MailboxSession,
  preferences: Pick<MailboxPreferences, "displayName" | "signature">,
): Promise<MailboxPreferences> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/preferences", {
    method: "PUT",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(preferences),
  });
  return response.json();
}

export async function createMailboxFolder(session: MailboxSession, folder: string): Promise<void> {
  await mutateMailboxFolder(session, "POST", { folder });
}

export async function renameMailboxFolder(session: MailboxSession, folder: string, targetFolder: string): Promise<void> {
  await mutateMailboxFolder(session, "PATCH", { folder, targetFolder });
}

export async function deleteMailboxFolder(session: MailboxSession, folder: string): Promise<void> {
  await mutateMailboxFolder(session, "DELETE", { folder });
}

export async function emptyMailboxFolder(session: MailboxSession, folder: string): Promise<{ deletedCount: number }> {
  const response = await request(session.apiBaseUrl, "/api/v1/mailbox/folder/empty", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder }),
  });
  return response.json();
}

export function normalizedApiBaseUrl(apiBaseUrl: string): string {
  return apiBaseUrl.trim().replace(/\/+$/, "");
}

function mailboxHeaders(session: MailboxSession): Record<string, string> {
  return { Authorization: `Bearer ${session.token}` };
}

async function request(apiBaseUrl: string, path: string, init: RequestInit): Promise<Response> {
  const response = await fetch(`${normalizedApiBaseUrl(apiBaseUrl)}${path}`, init);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response;
}

async function mutateMailboxFolder(
  session: MailboxSession,
  method: "POST" | "PATCH" | "DELETE",
  payload: Record<string, string>,
): Promise<void> {
  await request(session.apiBaseUrl, "/api/v1/mailbox/folder", {
    method,
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

function devicePlatform(): "ios" | "android" | "development" {
  const maybeNavigator = globalThis as { navigator?: { product?: string; userAgent?: string } };
  const userAgent = maybeNavigator.navigator?.userAgent?.toLowerCase() || "";
  if (userAgent.includes("android")) {
    return "android";
  }
  if (userAgent.includes("iphone") || userAgent.includes("ipad") || userAgent.includes("ios")) {
    return "ios";
  }
  return "development";
}
