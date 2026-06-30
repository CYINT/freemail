export type MailboxSession = {
  email: string;
  token: string;
  apiBaseUrl: string;
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
};

export type MailMessageDetail = MailMessage & {
  body: string;
  attachments: Array<{
    attachmentId: string;
    filename: string;
    contentType: string;
    size: number;
  }>;
};

export type MailboxSnapshot = {
  email: string;
  folders: MailFolder[];
  messages: MailMessage[];
};

export type ComposeMessage = {
  recipients: string[];
  subject: string;
  body: string;
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

export async function revokeMailboxSession(session: MailboxSession): Promise<void> {
  await request(session.apiBaseUrl, "/api/v1/mailbox/session", {
    method: "DELETE",
    headers: mailboxHeaders(session),
  });
}

export async function loadMailboxSnapshot(session: MailboxSession, folder = "INBOX"): Promise<MailboxSnapshot> {
  const path = `/api/v1/mailbox/snapshot?folder=${encodeURIComponent(folder)}&limit=25`;
  const response = await request(session.apiBaseUrl, path, { headers: mailboxHeaders(session) });
  return response.json();
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

export async function sendMailboxMessage(session: MailboxSession, message: ComposeMessage): Promise<void> {
  await request(session.apiBaseUrl, "/api/v1/mailbox/send", {
    method: "POST",
    headers: {
      ...mailboxHeaders(session),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(message),
  });
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
