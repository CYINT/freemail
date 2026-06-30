const loginForm = document.querySelector("#mailbox-login");
const folderNav = document.querySelector("#folder-nav");
const folderTools = document.querySelector("#folder-tools");
const folderNameInput = document.querySelector("#folder-name");
const folderRenameAction = document.querySelector("#folder-rename-action");
const folderDeleteAction = document.querySelector("#folder-delete-action");
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
const contactsAction = document.querySelector("#contacts-action");
const contactsList = document.querySelector("#contacts-list");
const composeTo = document.querySelector("#compose-to");
const composeSubject = document.querySelector("#compose-subject");
const composeBody = document.querySelector("#compose-body");
const composeAttachments = document.querySelector("#compose-attachments");
const adminAuthForm = document.querySelector("#admin-auth");
const adminApiBaseUrl = document.querySelector("#admin-api-base-url");
const adminTokenInput = document.querySelector("#admin-token");
const bootstrapTokenInput = document.querySelector("#bootstrap-token");
const adminStatus = document.querySelector("#admin-status");
const adminRefreshAction = document.querySelector("#admin-refresh-action");
const bootstrapAdminForm = document.querySelector("#bootstrap-admin-form");
const adminDomainForm = document.querySelector("#admin-domain-form");
const adminUserForm = document.querySelector("#admin-user-form");
const adminMailboxForm = document.querySelector("#admin-mailbox-form");
const adminAliasForm = document.querySelector("#admin-alias-form");
const adminDkimForm = document.querySelector("#admin-dkim-form");
const adminResults = document.querySelector("#admin-results");

const mailboxSessionStorageKey = "freemail.mailboxSession";
const adminSessionStorageKey = "freemail.adminSession";
const protectedFolders = ["inbox", "sent items", "drafts", "junk mail", "deleted items", "archive"];

let mailboxSession = {
  email: "",
  token: "",
  apiBaseUrl: "",
  folder: "INBOX",
};
let adminSession = {
  apiBaseUrl: "",
  adminToken: "",
  bootstrapToken: "",
};
let selectedMessageDetail = null;

restoreMailboxSession();
restoreAdminSession();

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

folderTools?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(folderTools);
  await createMailboxFolder(String(form.get("folderName") || "").trim());
});

folderRenameAction?.addEventListener("click", async () => {
  await renameMailboxFolder(String(folderNameInput?.value || "").trim());
});

folderDeleteAction?.addEventListener("click", async () => {
  await deleteMailboxFolder(mailboxSession.folder);
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

contactsAction?.addEventListener("click", async () => {
  await loadMailboxContacts();
});

logoutAction?.addEventListener("click", async () => {
  await revokeMailboxSession();
});

adminAuthForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(adminAuthForm);
  adminSession = {
    apiBaseUrl: String(form.get("apiBaseUrl") || "").trim().replace(/\/+$/, ""),
    adminToken: String(form.get("adminToken") || ""),
    bootstrapToken: String(form.get("bootstrapToken") || ""),
  };
  persistAdminSession(adminSession);
  setAdminStatus("Admin session saved in this browser profile.", "ready");
});

adminRefreshAction?.addEventListener("click", async () => {
  await loadAdminOverview();
});

bootstrapAdminForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(bootstrapAdminForm);
  await bootstrapAdministrator({
    domainName: String(form.get("domainName") || "").trim(),
    email: String(form.get("email") || "").trim(),
    displayName: String(form.get("displayName") || "").trim(),
    initialPassword: String(form.get("initialPassword") || ""),
    mailboxLocalPart: String(form.get("mailboxLocalPart") || "").trim(),
  });
});

adminDomainForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminDomainForm);
  await createAdminRecord("/api/v1/admin/domains", { name: String(form.get("name") || "").trim() }, "Domain created.");
});

adminUserForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminUserForm);
  await createAdminRecord(
    "/api/v1/admin/users",
    {
      email: String(form.get("email") || "").trim(),
      displayName: String(form.get("displayName") || "").trim(),
      initialPassword: String(form.get("initialPassword") || ""),
      isAdmin: form.get("isAdmin") === "on",
    },
    "User invited.",
  );
});

adminMailboxForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminMailboxForm);
  await createAdminRecord(
    "/api/v1/admin/mailboxes",
    {
      userId: Number(form.get("userId")),
      domainId: Number(form.get("domainId")),
      localPart: String(form.get("localPart") || "").trim(),
    },
    "Mailbox created.",
  );
});

adminAliasForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminAliasForm);
  await createAdminRecord(
    "/api/v1/admin/aliases",
    {
      source: String(form.get("source") || "").trim(),
      destination: String(form.get("destination") || "").trim(),
    },
    "Alias created.",
  );
});

adminDkimForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminDkimForm);
  await createAdminRecord(
    "/api/v1/admin/dkim-keys",
    {
      domainId: Number(form.get("domainId")),
      selector: String(form.get("selector") || "").trim(),
    },
    "DKIM key generated. Store the returned private key outside Git.",
  );
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
    loadMailboxContacts({ quiet: true });
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

async function loadMailboxContacts({ quiet = false } = {}) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    if (!quiet) {
      setStatus("Sign in to load contacts.", "error");
    }
    return;
  }
  if (!quiet) {
    setStatus("Loading contacts...", "loading");
  }
  try {
    const url = new URL("/api/v1/mailbox/contacts", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", mailboxSession.folder || "INBOX");
    url.searchParams.set("limit", "100");
    const response = await fetch(url, {
      headers: mailboxHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderContacts(result.contacts || []);
    if (!quiet) {
      setStatus(`Loaded ${result.contacts?.length || 0} contacts.`, "ready");
    }
  } catch (error) {
    if (!quiet) {
      setStatus(`Contacts load failed: ${readableError(error)}`, "error");
    }
  }
}

async function createMailboxFolder(folder) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in before creating folders.", "error");
    return;
  }
  if (!validFolderName(folder)) {
    setStatus("Enter a folder name without quotes or slashes.", "error");
    return;
  }
  setStatus(`Creating ${folder}...`, "loading");
  try {
    await mutateMailboxFolder("POST", { folder });
    await loadMailboxSnapshot(folder);
    setStatus(`Created ${folder}.`, "ready");
  } catch (error) {
    setStatus(`Create folder failed: ${readableError(error)}`, "error");
  }
}

async function renameMailboxFolder(targetFolder) {
  const folder = mailboxSession.folder;
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in before renaming folders.", "error");
    return;
  }
  if (protectedFolder(folder)) {
    setStatus("Core folders cannot be renamed.", "error");
    return;
  }
  if (!validFolderName(targetFolder)) {
    setStatus("Enter a new folder name without quotes or slashes.", "error");
    return;
  }
  if (targetFolder === folder) {
    setStatus("Enter a different folder name before renaming.", "error");
    return;
  }
  setStatus(`Renaming ${folder}...`, "loading");
  try {
    await mutateMailboxFolder("PATCH", { folder, targetFolder });
    await loadMailboxSnapshot(targetFolder);
    setStatus(`Renamed ${folder} to ${targetFolder}.`, "ready");
  } catch (error) {
    setStatus(`Rename folder failed: ${readableError(error)}`, "error");
  }
}

async function deleteMailboxFolder(folder) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in before deleting folders.", "error");
    return;
  }
  if (protectedFolder(folder)) {
    setStatus("Core folders cannot be deleted.", "error");
    return;
  }
  if (!window.confirm(`Delete folder "${folder}"?`)) {
    return;
  }
  setStatus(`Deleting ${folder}...`, "loading");
  try {
    await mutateMailboxFolder("DELETE", { folder });
    await loadMailboxSnapshot("INBOX");
    setStatus(`Deleted ${folder}.`, "ready");
  } catch (error) {
    setStatus(`Delete folder failed: ${readableError(error)}`, "error");
  }
}

async function mutateMailboxFolder(method, payload) {
  const response = await fetch(new URL("/api/v1/mailbox/folder", mailboxSession.apiBaseUrl), {
    method,
    headers: {
      ...mailboxHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
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

function renderContacts(contacts) {
  if (!contactsList) {
    return;
  }
  if (!contacts.length) {
    contactsList.replaceChildren(emptyContactsMessage());
    return;
  }
  contactsList.replaceChildren(
    ...contacts.slice(0, 12).map((contact) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "contact-item";
      button.title = contact.email;
      button.innerHTML = `
        <span>${escapeHtml(contact.name || contact.email)}</span>
        <small>${escapeHtml(contact.email)} - ${contact.messageCount || 1}</small>
      `;
      button.addEventListener("click", () => {
        addComposeRecipient(contact.email);
        setStatus(`Added ${contact.email} to compose.`, "ready");
      });
      return button;
    }),
  );
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
  renderFolderTools(activeFolder);
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

function addComposeRecipient(email) {
  if (!composeTo || !email) {
    return;
  }
  const existing = composeTo.value
    .split(",")
    .map((recipient) => recipient.trim())
    .filter(Boolean);
  if (!existing.map((recipient) => recipient.toLowerCase()).includes(email.toLowerCase())) {
    existing.push(email);
  }
  composeTo.value = existing.join(", ");
  composeTo.focus();
}

function renderFolderTools(activeFolder) {
  if (folderNameInput) {
    folderNameInput.value = protectedFolder(activeFolder) ? "" : activeFolder;
    folderNameInput.placeholder = protectedFolder(activeFolder) ? "New folder" : "Rename current folder";
  }
  const disabled = protectedFolder(activeFolder);
  if (folderRenameAction) {
    folderRenameAction.disabled = disabled;
  }
  if (folderDeleteAction) {
    folderDeleteAction.disabled = disabled;
  }
}

function validFolderName(folder) {
  return Boolean(folder && !/[\\/"\r\n]/.test(folder));
}

function protectedFolder(folder) {
  return protectedFolders.includes(String(folder || "").trim().toLowerCase());
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

async function bootstrapAdministrator(payload) {
  if (!adminSession.apiBaseUrl || !adminSession.bootstrapToken) {
    setAdminStatus("Save API and bootstrap token before bootstrapping.", "error");
    return;
  }
  setAdminStatus("Bootstrapping administrator...", "loading");
  try {
    const response = await fetch(new URL("/api/v1/bootstrap/admin", adminSession.apiBaseUrl), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-FreeMail-Bootstrap-Token": adminSession.bootstrapToken,
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderAdminResult("Bootstrap administrator", result);
    setAdminStatus("Administrator bootstrapped.", "ready");
    await loadAdminOverview({ quiet: true });
  } catch (error) {
    setAdminStatus(`Bootstrap failed: ${readableError(error)}`, "error");
  }
}

async function createAdminRecord(path, payload, successMessage) {
  if (!adminSession.apiBaseUrl || !adminSession.adminToken) {
    setAdminStatus("Save API and admin token before making admin changes.", "error");
    return;
  }
  setAdminStatus("Saving admin change...", "loading");
  try {
    const response = await fetch(new URL(path, adminSession.apiBaseUrl), {
      method: "POST",
      headers: adminHeaders(),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderAdminResult(successMessage, result);
    setAdminStatus(successMessage, "ready");
    await loadAdminOverview({ quiet: true });
  } catch (error) {
    setAdminStatus(`Admin change failed: ${readableError(error)}`, "error");
  }
}

async function loadAdminOverview({ quiet = false } = {}) {
  if (!adminSession.apiBaseUrl || !adminSession.adminToken) {
    setAdminStatus("Save API and admin token before loading admin metadata.", "error");
    return;
  }
  if (!quiet) {
    setAdminStatus("Loading admin metadata...", "loading");
  }
  try {
    const [domains, users, mailboxes, aliases, dkimKeys, auditLog] = await Promise.all(
      [
        "/api/v1/admin/domains",
        "/api/v1/admin/users",
        "/api/v1/admin/mailboxes",
        "/api/v1/admin/aliases",
        "/api/v1/admin/dkim-keys",
        "/api/v1/admin/audit-log",
      ].map(fetchAdminJson),
    );
    renderAdminOverview({ domains, users, mailboxes, aliases, dkimKeys, auditLog });
    if (!quiet) {
      setAdminStatus("Admin metadata loaded.", "ready");
    }
  } catch (error) {
    setAdminStatus(`Admin load failed: ${readableError(error)}`, "error");
  }
}

async function fetchAdminJson(path) {
  const response = await fetch(new URL(path, adminSession.apiBaseUrl), {
    headers: adminHeaders(),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function adminHeaders() {
  return {
    "Content-Type": "application/json",
    "X-FreeMail-Admin-Token": adminSession.adminToken,
  };
}

function renderAdminOverview({ domains, users, mailboxes, aliases, dkimKeys, auditLog }) {
  if (!adminResults) {
    return;
  }
  adminResults.replaceChildren(
    adminTable("Domains", domains, ["id", "name", "status"], {
      statusPath: "/api/v1/admin/domains",
      statusActiveValue: "active",
      extraActions: [domainDnsAction],
    }),
    adminTable("Users", users, ["id", "email", "displayName", "isAdmin", "status"], {
      statusPath: "/api/v1/admin/users",
      statusActiveValue: "invited",
    }),
    adminTable("Mailboxes", mailboxes, ["id", "address", "userId", "status"], {
      statusPath: "/api/v1/admin/mailboxes",
      statusActiveValue: "active",
    }),
    adminTable("Aliases", aliases, ["id", "source", "destination", "status"], {
      statusPath: "/api/v1/admin/aliases",
      statusActiveValue: "active",
    }),
    adminTable("DKIM keys", dkimKeys, ["id", "domainId", "selector", "dnsName", "status"], {
      statusPath: "/api/v1/admin/dkim-keys",
      statusActiveValue: "active",
    }),
    adminTable("Audit log", auditLog.slice(0, 10), ["id", "actor", "action", "targetType", "targetId", "createdAt"]),
  );
}

function renderAdminResult(title, result) {
  if (!adminResults) {
    return;
  }
  const section = document.createElement("section");
  section.className = "admin-result-card";
  const heading = document.createElement("h3");
  heading.textContent = title;
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(result, null, 2);
  section.replaceChildren(heading, pre);
  adminResults.replaceChildren(section);
}

function adminTable(title, rows, columns, options = {}) {
  const section = document.createElement("section");
  section.className = "admin-result-card";
  const heading = document.createElement("h3");
  heading.textContent = `${title} (${rows.length})`;
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.textContent = "No records yet.";
    section.replaceChildren(heading, empty);
    return section;
  }
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headerRow.replaceChildren(
    ...columns.map(tableHeader),
    ...(adminTableHasActions(options) ? [tableHeader("actions")] : []),
  );
  thead.replaceChildren(headerRow);
  const tbody = document.createElement("tbody");
  tbody.replaceChildren(
    ...rows.map((row) => {
      const tableRow = document.createElement("tr");
      tableRow.replaceChildren(
        ...columns.map((column) => tableCell(row[column])),
        ...(adminTableHasActions(options) ? [adminActionsCell(row, options)] : []),
      );
      return tableRow;
    }),
  );
  table.replaceChildren(thead, tbody);
  section.replaceChildren(heading, table);
  return section;
}

function adminTableHasActions(options) {
  return Boolean(options.statusPath || options.extraActions?.length);
}

function adminActionsCell(row, options) {
  const cell = document.createElement("td");
  const actions = document.createElement("div");
  actions.className = "admin-row-actions";
  if (options.statusPath) {
    actions.append(
      adminActionButton("Suspend", () => updateAdminStatus(options.statusPath, row.id, "suspended")),
      adminActionButton(options.statusActiveValue === "invited" ? "Invite" : "Activate", () =>
        updateAdminStatus(options.statusPath, row.id, options.statusActiveValue),
      ),
    );
  }
  for (const actionFactory of options.extraActions || []) {
    actions.append(actionFactory(row));
  }
  cell.append(actions);
  return cell;
}

function adminActionButton(label, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "admin-row-action";
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function domainDnsAction(row) {
  return adminActionButton("DNS", () => loadDomainDnsGuidance(row.id));
}

async function updateAdminStatus(basePath, recordId, statusValue) {
  if (!adminSession.apiBaseUrl || !adminSession.adminToken) {
    setAdminStatus("Save API and admin token before changing status.", "error");
    return;
  }
  setAdminStatus(`Updating status to ${statusValue}...`, "loading");
  try {
    const response = await fetch(new URL(`${basePath}/${recordId}/status`, adminSession.apiBaseUrl), {
      method: "PATCH",
      headers: adminHeaders(),
      body: JSON.stringify({ status: statusValue }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderAdminResult("Status updated", result);
    setAdminStatus("Status updated.", "ready");
    await loadAdminOverview({ quiet: true });
  } catch (error) {
    setAdminStatus(`Status update failed: ${readableError(error)}`, "error");
  }
}

async function loadDomainDnsGuidance(domainId) {
  if (!adminSession.apiBaseUrl || !adminSession.adminToken) {
    setAdminStatus("Save API and admin token before loading DNS guidance.", "error");
    return;
  }
  setAdminStatus("Loading DNS guidance...", "loading");
  try {
    const response = await fetch(new URL(`/api/v1/admin/domains/${domainId}/dns`, adminSession.apiBaseUrl), {
      headers: adminHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderAdminResult(`DNS guidance for ${result.domain || `domain ${domainId}`}`, result);
    setAdminStatus("DNS guidance loaded.", "ready");
  } catch (error) {
    setAdminStatus(`DNS guidance failed: ${readableError(error)}`, "error");
  }
}

function tableHeader(value) {
  const cell = document.createElement("th");
  cell.textContent = value;
  return cell;
}

function tableCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value === undefined || value === null ? "" : String(value);
  return cell;
}

function restoreAdminSession() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(adminSessionStorageKey) || "null");
    if (!stored?.apiBaseUrl) {
      return;
    }
    adminSession = {
      apiBaseUrl: String(stored.apiBaseUrl).replace(/\/+$/, ""),
      adminToken: String(stored.adminToken || ""),
      bootstrapToken: String(stored.bootstrapToken || ""),
    };
    if (adminApiBaseUrl) {
      adminApiBaseUrl.value = adminSession.apiBaseUrl;
    }
    if (adminTokenInput) {
      adminTokenInput.value = adminSession.adminToken;
    }
    if (bootstrapTokenInput) {
      bootstrapTokenInput.value = adminSession.bootstrapToken;
    }
  } catch (_error) {
    forgetAdminSession();
  }
}

function persistAdminSession(session) {
  window.localStorage.setItem(
    adminSessionStorageKey,
    JSON.stringify({
      apiBaseUrl: session.apiBaseUrl,
      adminToken: session.adminToken,
      bootstrapToken: session.bootstrapToken,
    }),
  );
}

function forgetAdminSession() {
  window.localStorage.removeItem(adminSessionStorageKey);
  adminSession = { apiBaseUrl: "", adminToken: "", bootstrapToken: "" };
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

function emptyContactsMessage() {
  const node = document.createElement("p");
  node.textContent = "No contacts found in this folder yet.";
  return node;
}

function setStatus(message, state) {
  if (!statusNode) {
    return;
  }
  statusNode.textContent = message;
  statusNode.dataset.state = state;
}

function setAdminStatus(message, state) {
  if (!adminStatus) {
    return;
  }
  adminStatus.textContent = message;
  adminStatus.dataset.state = state;
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
