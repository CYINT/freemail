const loginForm = document.querySelector("#mailbox-login");
const folderNav = document.querySelector("#folder-nav");
const messageList = document.querySelector("#message-list");
const statusNode = document.querySelector("#mailbox-status");
const readerSubject = document.querySelector("#reader-subject");
const readerMeta = document.querySelector("#reader-meta");
const messageBody = document.querySelector("#message-body");
const messageAttachments = document.querySelector("#message-attachments");
const composeForm = document.querySelector("#compose-form");
const searchForm = document.querySelector("#mailbox-search");
const searchQuery = document.querySelector("#search-query");
const logoutAction = document.querySelector("#mailbox-logout");
const replyAction = document.querySelector("#reply-action");
const forwardAction = document.querySelector("#forward-action");
const archiveAction = document.querySelector("#archive-action");
const spamAction = document.querySelector("#spam-action");
const deleteAction = document.querySelector("#delete-action");
const composeTo = document.querySelector("#compose-to");
const composeSubject = document.querySelector("#compose-subject");
const composeBody = document.querySelector("#compose-body");
const composeAttachments = document.querySelector("#compose-attachments");

const mailboxSessionStorageKey = "freemail.mailboxSession";

let mailboxSession = {
  email: "",
  token: "",
  apiBaseUrl: "",
  folder: "INBOX",
};
let selectedMessageDetail = null;

restoreMailboxSession();

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(loginForm);
  await createMailboxSession({
    email: String(form.get("email") || "").trim(),
    password: String(form.get("password") || ""),
    apiBaseUrl: String(form.get("apiBaseUrl") || "").trim().replace(/\/+$/, ""),
  });
});

composeForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(composeForm);
  await sendMailboxMessage({
    recipients: String(form.get("to") || "")
      .split(",")
      .map((recipient) => recipient.trim())
      .filter(Boolean),
    subject: String(form.get("subject") || "").trim(),
    body: String(form.get("body") || ""),
    attachments: await filesToAttachments(composeAttachments?.files || []),
  });
});

searchForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(searchForm);
  await searchMailboxMessages(String(form.get("query") || "").trim());
});

replyAction?.addEventListener("click", () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before replying.", "error");
    return;
  }
  prefillReply(selectedMessageDetail);
});

forwardAction?.addEventListener("click", () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before forwarding.", "error");
    return;
  }
  prefillForward(selectedMessageDetail);
});

archiveAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before archiving.", "error");
    return;
  }
  await archiveMailboxMessage(selectedMessageDetail);
});

spamAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before marking spam.", "error");
    return;
  }
  await moveMailboxMessage(selectedMessageDetail, "Junk Mail", "Message moved to spam.");
});

deleteAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before deleting.", "error");
    return;
  }
  await moveMailboxMessage(selectedMessageDetail, "Deleted Items", "Message moved to trash.");
});

logoutAction?.addEventListener("click", async () => {
  await revokeMailboxSession();
});

async function createMailboxSession({ email, password, apiBaseUrl }) {
  if (!email || !password || !apiBaseUrl) {
    setStatus("Enter mailbox credentials to start a session.", "error");
    return;
  }
  setStatus("Starting mailbox session...", "loading");
  try {
    const url = new URL("/api/v1/mailbox/session", apiBaseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const session = await response.json();
    mailboxSession = {
      email: session.email || email,
      token: session.token,
      apiBaseUrl,
      folder: mailboxSession.folder || "INBOX",
    };
    persistMailboxSession(mailboxSession);
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    forgetMailboxSession();
    setStatus(`Session start failed: ${readableError(error)}`, "error");
  }
}

async function revokeMailboxSession() {
  const token = mailboxSession.token;
  const apiBaseUrl = mailboxSession.apiBaseUrl;
  forgetMailboxSession();
  if (token && apiBaseUrl) {
    try {
      await fetch(new URL("/api/v1/mailbox/session", apiBaseUrl), {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (_error) {
      // Local cleanup is authoritative for the browser; server expiry will clean stale sessions.
    }
  }
  renderFolders([], "INBOX");
  renderMessages([]);
  setStatus("Signed out.", "idle");
}

async function loadMailboxSnapshot(folder) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in to load live mail.", "idle");
    return;
  }
  setStatus(`Loading ${folder}...`, "loading");
  try {
    const url = new URL("/api/v1/mailbox/snapshot", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", folder);
    url.searchParams.set("limit", "25");
    const response = await fetch(url, {
      headers: mailboxHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const snapshot = await response.json();
    mailboxSession.folder = folder;
    persistMailboxSession(mailboxSession);
    clearSearch();
    renderFolders(snapshot.folders || [], folder);
    renderMessages(snapshot.messages || []);
    setStatus(`Loaded ${snapshot.messages?.length || 0} messages from ${folder}.`, "ready");
  } catch (error) {
    setStatus(`Mailbox load failed: ${readableError(error)}`, "error");
  }
}

async function searchMailboxMessages(query) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in to search mail.", "error");
    return;
  }
  if (!query) {
    await loadMailboxSnapshot(mailboxSession.folder);
    return;
  }
  setStatus(`Searching ${mailboxSession.folder}...`, "loading");
  try {
    const url = new URL("/api/v1/mailbox/search", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", mailboxSession.folder);
    url.searchParams.set("query", query);
    url.searchParams.set("limit", "25");
    const response = await fetch(url, {
      headers: mailboxHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderMessages(result.messages || []);
    setStatus(`Found ${result.messages?.length || 0} messages for "${query}".`, "ready");
  } catch (error) {
    setStatus(`Search failed: ${readableError(error)}`, "error");
  }
}

async function archiveMailboxMessage(message) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before archiving.", "error");
    return;
  }
  setStatus("Archiving message...", "loading");
  try {
    const url = new URL("/api/v1/mailbox/message/archive", mailboxSession.apiBaseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        folder: message.folder,
        messageId: message.messageId,
        archiveFolder: "Archive",
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    setStatus("Message archived.", "ready");
    selectedMessageDetail = null;
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    setStatus(`Archive failed: ${readableError(error)}`, "error");
  }
}

async function moveMailboxMessage(message, targetFolder, successMessage) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before moving messages.", "error");
    return;
  }
  setStatus(`Moving message to ${targetFolder}...`, "loading");
  try {
    const url = new URL("/api/v1/mailbox/message/move", mailboxSession.apiBaseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        folder: message.folder,
        messageId: message.messageId,
        targetFolder,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    setStatus(successMessage, "ready");
    selectedMessageDetail = null;
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    setStatus(`Move failed: ${readableError(error)}`, "error");
  }
}

async function sendMailboxMessage(message) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before sending.", "error");
    return;
  }
  setStatus("Sending message...", "loading");
  try {
    const url = new URL("/api/v1/mailbox/send", mailboxSession.apiBaseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(message),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    setStatus(`Sent ${result.messageId || "message"}.`, "ready");
    if (composeAttachments) {
      composeAttachments.value = "";
    }
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    setStatus(`Send failed: ${readableError(error)}`, "error");
  }
}

function renderFolders(folders, activeFolder) {
  if (!folderNav) {
    return;
  }
  folderNav.replaceChildren(
    ...folders.map((folder) => {
      const link = document.createElement("a");
      link.href = `#${encodeURIComponent(folder.name)}`;
      link.dataset.folder = folder.name;
      link.className = folder.name === activeFolder ? "active" : "";
      link.innerHTML = `<span>${escapeHtml(folder.name)}</span><span>${folder.unreadCount || folder.messageCount || 0}</span>`;
      link.addEventListener("click", (event) => {
        event.preventDefault();
        loadMailboxSnapshot(folder.name);
      });
      return link;
    }),
  );
}

function renderMessages(messages) {
  if (!messageList) {
    return;
  }
  if (!messages.length) {
    selectedMessageDetail = null;
    messageList.replaceChildren(emptyMessage());
    readerSubject.textContent = "No messages";
    readerMeta.textContent = "Select another folder or refresh the mailbox.";
    renderMessageBody("This folder is empty.");
    renderMessageAttachments(null);
    return;
  }
  const rows = messages.map((message, index) => messageRow(message, index === 0));
  messageList.replaceChildren(...rows);
  selectMessage(messages[0], rows[0]);
}

function messageRow(message, selected) {
  const row = document.createElement("article");
  row.className = `message-row${selected ? " selected" : ""}${message.unread ? " unread" : ""}`;
  row.tabIndex = 0;
  row.innerHTML = `
    <span class="sender">${escapeHtml(message.sender || "Unknown sender")}</span>
    <strong>${escapeHtml(message.subject || "(no subject)")}</strong>
    <p>${escapeHtml(message.recipients || "")}</p>
    <time>${escapeHtml(shortDate(message.date))}</time>
  `;
  row.addEventListener("click", () => selectMessage(message, row));
  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectMessage(message, row);
    }
  });
  return row;
}

async function selectMessage(message, row) {
  document.querySelectorAll(".message-row.selected").forEach((selectedRow) => {
    selectedRow.classList.remove("selected");
  });
  row.classList.add("selected");
  readerSubject.textContent = message.subject || "(no subject)";
  readerMeta.textContent = `From ${message.sender || "Unknown sender"} to ${message.recipients || mailboxSession.email}`;
  renderMessageBody("Loading message...");
  try {
    const detail = await loadMailboxMessage(message.folder, message.messageId);
    selectedMessageDetail = detail;
    readerSubject.textContent = detail.subject || "(no subject)";
    readerMeta.textContent = `From ${detail.sender || "Unknown sender"} to ${detail.recipients || mailboxSession.email}`;
    renderMessageBody(detail.body || "(No plain text body)");
    renderMessageAttachments(detail);
  } catch (error) {
    selectedMessageDetail = null;
    renderMessageBody(`Message load failed: ${readableError(error)}`);
    renderMessageAttachments(null);
  }
}

function prefillReply(message) {
  fillCompose({
    to: addressOnly(message.sender),
    subject: prefixedSubject("Re:", message.subject),
    body: quoteMessage(message, "reply"),
  });
  setStatus("Reply draft ready.", "ready");
}

function prefillForward(message) {
  fillCompose({
    to: "",
    subject: prefixedSubject("Fwd:", message.subject),
    body: quoteMessage(message, "forward"),
  });
  setStatus("Forward draft ready.", "ready");
}

function fillCompose({ to, subject, body }) {
  if (composeTo) {
    composeTo.value = to;
  }
  if (composeSubject) {
    composeSubject.value = subject;
  }
  if (composeBody) {
    composeBody.value = body;
    composeBody.focus();
  }
}

function prefixedSubject(prefix, subject) {
  const cleanSubject = subject || "(no subject)";
  return cleanSubject.toLowerCase().startsWith(prefix.toLowerCase()) ? cleanSubject : `${prefix} ${cleanSubject}`;
}

function quoteMessage(message, mode) {
  const label = mode === "forward" ? "Forwarded message" : "Original message";
  const lines = [
    "",
    "",
    `---- ${label} ----`,
    `From: ${message.sender || "Unknown sender"}`,
    `To: ${message.recipients || mailboxSession.email}`,
    `Subject: ${message.subject || "(no subject)"}`,
    "",
    message.body || "",
  ];
  return lines.join("\n");
}

function addressOnly(value) {
  const match = String(value || "").match(/<([^>]+)>/);
  return match ? match[1] : String(value || "").trim();
}

async function loadMailboxMessage(folder, messageId) {
  const url = new URL("/api/v1/mailbox/message", mailboxSession.apiBaseUrl);
  url.searchParams.set("folder", folder);
  url.searchParams.set("message_id", messageId);
  const response = await fetch(url, {
    headers: mailboxHeaders(),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function downloadMailboxAttachment(message, attachment) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before downloading attachments.", "error");
    return;
  }
  setStatus(`Downloading ${attachment.filename || "attachment"}...`, "loading");
  try {
    const url = new URL("/api/v1/mailbox/message/attachment", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", message.folder);
    url.searchParams.set("message_id", message.messageId);
    url.searchParams.set("attachment_id", attachment.attachmentId);
    const response = await fetch(url, {
      headers: mailboxHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = attachment.filename || "attachment";
    link.click();
    URL.revokeObjectURL(href);
    setStatus(`Downloaded ${attachment.filename || "attachment"}.`, "ready");
  } catch (error) {
    setStatus(`Attachment download failed: ${readableError(error)}`, "error");
  }
}

function renderMessageBody(body) {
  if (!messageBody) {
    return;
  }
  const paragraphs = String(body || "")
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
  messageBody.replaceChildren(
    ...(paragraphs.length ? paragraphs : [""])
      .map((paragraph) => {
        const node = document.createElement("p");
        node.textContent = paragraph;
        return node;
      }),
  );
}

function renderMessageAttachments(message) {
  if (!messageAttachments) {
    return;
  }
  const attachments = message?.attachments || [];
  if (!attachments.length) {
    messageAttachments.replaceChildren();
    return;
  }
  const heading = document.createElement("h3");
  heading.textContent = "Attachments";
  const buttons = attachments.map((attachment) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "attachment-download";
    button.textContent = `${attachment.filename || "attachment"} (${formatBytes(attachment.size || 0)})`;
    button.addEventListener("click", () => downloadMailboxAttachment(message, attachment));
    return button;
  });
  messageAttachments.replaceChildren(heading, ...buttons);
}

function mailboxHeaders() {
  return mailboxSession.token ? { Authorization: `Bearer ${mailboxSession.token}` } : {};
}

function restoreMailboxSession() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(mailboxSessionStorageKey) || "null");
    if (!stored?.token || !stored?.apiBaseUrl) {
      return;
    }
    mailboxSession = {
      email: String(stored.email || ""),
      token: String(stored.token),
      apiBaseUrl: String(stored.apiBaseUrl).replace(/\/+$/, ""),
      folder: String(stored.folder || "INBOX"),
    };
    const apiInput = document.querySelector("#api-base-url");
    const emailInput = document.querySelector("#mailbox-email");
    if (apiInput) {
      apiInput.value = mailboxSession.apiBaseUrl;
    }
    if (emailInput) {
      emailInput.value = mailboxSession.email;
    }
    loadMailboxSnapshot(mailboxSession.folder);
  } catch (_error) {
    forgetMailboxSession();
  }
}

function persistMailboxSession(session) {
  window.localStorage.setItem(
    mailboxSessionStorageKey,
    JSON.stringify({
      email: session.email,
      token: session.token,
      apiBaseUrl: session.apiBaseUrl,
      folder: session.folder,
    }),
  );
}

function forgetMailboxSession() {
  window.localStorage.removeItem(mailboxSessionStorageKey);
  mailboxSession = { email: "", token: "", apiBaseUrl: "", folder: "INBOX" };
  selectedMessageDetail = null;
  clearSearch();
}

function clearSearch() {
  if (searchQuery) {
    searchQuery.value = "";
  }
}

async function filesToAttachments(files) {
  return Promise.all(
    Array.from(files).map(async (file) => ({
      filename: file.name,
      contentType: file.type || "application/octet-stream",
      contentBase64: await fileToBase64(file),
    })),
  );
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",", 2)[1] : value);
    });
    reader.addEventListener("error", () => reject(reader.error || new Error("file read failed")));
    reader.readAsDataURL(file);
  });
}

function formatBytes(value) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function emptyMessage() {
  const row = document.createElement("article");
  row.className = "message-row selected";
  row.tabIndex = 0;
  row.innerHTML = "<span class=\"sender\">FreeMail</span><strong>No messages</strong><p>This folder is empty.</p><time></time>";
  return row;
}

function setStatus(message, state) {
  if (!statusNode) {
    return;
  }
  statusNode.textContent = message;
  statusNode.dataset.state = state;
}

function shortDate(value) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function readableError(error) {
  if (error instanceof Error) {
    return error.message.slice(0, 180);
  }
  return "unknown error";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
