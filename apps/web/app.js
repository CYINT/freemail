const loginForm = document.querySelector("#mailbox-login");
const folderNav = document.querySelector("#folder-nav");
const folderTools = document.querySelector("#folder-tools");
const folderNameInput = document.querySelector("#folder-name");
const folderRenameAction = document.querySelector("#folder-rename-action");
const folderEmptyAction = document.querySelector("#folder-empty-action");
const folderDeleteAction = document.querySelector("#folder-delete-action");
const messageList = document.querySelector("#message-list");
const bulkToolbar = document.querySelector(".bulk-toolbar");
const loadMoreAction = document.querySelector("#load-more-action");
const statusNode = document.querySelector("#mailbox-status");
const readerSubject = document.querySelector("#reader-subject");
const readerMeta = document.querySelector("#reader-meta");
const messageBody = document.querySelector("#message-body");
const messageHeaders = document.querySelector("#message-headers");
const messageAttachments = document.querySelector("#message-attachments");
const composeForm = document.querySelector("#compose-form");
const saveDraftAction = document.querySelector("#save-draft-action");
const searchForm = document.querySelector("#mailbox-search");
const searchQuery = document.querySelector("#search-query");
const logoutAction = document.querySelector("#mailbox-logout");
const replyAction = document.querySelector("#reply-action");
const forwardAction = document.querySelector("#forward-action");
const loadThreadAction = document.querySelector("#load-thread-action");
const headersAction = document.querySelector("#headers-action");
const editDraftAction = document.querySelector("#edit-draft-action");
const downloadSourceAction = document.querySelector("#download-source-action");
const importSourceAction = document.querySelector("#import-source-action");
const importSourceFile = document.querySelector("#import-source-file");
const starAction = document.querySelector("#star-action");
const unstarAction = document.querySelector("#unstar-action");
const markReadAction = document.querySelector("#mark-read-action");
const markUnreadAction = document.querySelector("#mark-unread-action");
const archiveAction = document.querySelector("#archive-action");
const spamAction = document.querySelector("#spam-action");
const deleteAction = document.querySelector("#delete-action");
const bulkReadAction = document.querySelector("#bulk-read-action");
const bulkUnreadAction = document.querySelector("#bulk-unread-action");
const bulkStarAction = document.querySelector("#bulk-star-action");
const bulkUnstarAction = document.querySelector("#bulk-unstar-action");
const bulkArchiveAction = document.querySelector("#bulk-archive-action");
const bulkSpamAction = document.querySelector("#bulk-spam-action");
const bulkDeleteAction = document.querySelector("#bulk-delete-action");
const contactsAction = document.querySelector("#contacts-action");
const contactsList = document.querySelector("#contacts-list");
const savedContactForm = document.querySelector("#saved-contact-form");
const savedContactName = document.querySelector("#saved-contact-name");
const savedContactEmail = document.querySelector("#saved-contact-email");
const preferencesForm = document.querySelector("#mailbox-preferences");
const preferenceDisplayName = document.querySelector("#preference-display-name");
const preferenceSignature = document.querySelector("#preference-signature");
const composeTo = document.querySelector("#compose-to");
const composeSubject = document.querySelector("#compose-subject");
const composeBody = document.querySelector("#compose-body");
const composeAttachments = document.querySelector("#compose-attachments");
const adminAuthForm = document.querySelector("#admin-auth");
const adminApiBaseUrl = document.querySelector("#admin-api-base-url");
const adminEmailInput = document.querySelector("#admin-email");
const adminPasswordInput = document.querySelector("#admin-password");
const adminTotpCodeInput = document.querySelector("#admin-totp-code");
const adminTokenInput = document.querySelector("#admin-token");
const bootstrapTokenInput = document.querySelector("#bootstrap-token");
const adminStatus = document.querySelector("#admin-status");
const adminLogoutAction = document.querySelector("#admin-logout");
const adminSyncPlanAction = document.querySelector("#admin-sync-plan-action");
const adminRefreshAction = document.querySelector("#admin-refresh-action");
const bootstrapAdminForm = document.querySelector("#bootstrap-admin-form");
const adminDomainForm = document.querySelector("#admin-domain-form");
const adminUserForm = document.querySelector("#admin-user-form");
const adminMfaForm = document.querySelector("#admin-mfa-form");
const adminMfaSetupAction = document.querySelector("#admin-mfa-setup-action");
const adminMfaDisableAction = document.querySelector("#admin-mfa-disable-action");
const adminUserPasswordForm = document.querySelector("#admin-user-password-form");
const adminMailboxForm = document.querySelector("#admin-mailbox-form");
const adminMailboxQuotaForm = document.querySelector("#admin-mailbox-quota-form");
const adminAliasForm = document.querySelector("#admin-alias-form");
const adminDkimForm = document.querySelector("#admin-dkim-form");
const adminResults = document.querySelector("#admin-results");

const mailboxSessionStorageKey = "freemail.mailboxSession";
const adminSessionStorageKey = "freemail.adminSession";
const protectedFolders = ["inbox", "sent items", "drafts", "junk mail", "deleted items", "archive"];
const emptyProtectedFolders = ["inbox", "sent items", "drafts", "archive"];
const mailboxPageSize = 25;

let mailboxSession = {
  email: "",
  token: "",
  apiBaseUrl: "",
  folder: "INBOX",
};
let adminSession = {
  apiBaseUrl: "",
  adminToken: "",
  adminBearerToken: "",
  adminEmail: "",
  bootstrapToken: "",
};
let selectedMessageDetail = null;
let selectedMessageIds = new Set();
let visibleMessages = [];
let mailboxPagination = {
  mode: "folder",
  query: "",
  nextOffset: null,
  hasMore: false,
};
let mailboxPreferences = {
  displayName: "",
  signature: "",
};

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
  await sendMailboxMessage(await composePayload());
});

saveDraftAction?.addEventListener("click", async () => {
  await saveMailboxDraft(await composePayload());
});

loadMoreAction?.addEventListener("click", async () => {
  await loadMoreMailboxMessages();
});

preferencesForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveMailboxPreferences();
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

folderEmptyAction?.addEventListener("click", async () => {
  await emptyMailboxFolder(mailboxSession.folder);
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

loadThreadAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail?.threadId) {
    setStatus("Select a message before loading the conversation.", "error");
    return;
  }
  await loadMailboxThread(selectedMessageDetail);
});

headersAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before loading headers.", "error");
    return;
  }
  await loadMailboxMessageHeaders(selectedMessageDetail);
});

editDraftAction?.addEventListener("click", () => {
  if (!selectedMessageDetail || !isDraftMessage(selectedMessageDetail)) {
    setStatus("Select a saved draft before editing.", "error");
    return;
  }
  prefillSavedDraft(selectedMessageDetail);
});

downloadSourceAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before downloading EML.", "error");
    return;
  }
  await downloadMailboxMessageSource(selectedMessageDetail);
});

importSourceAction?.addEventListener("click", () => {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before importing EML.", "error");
    return;
  }
  importSourceFile?.click();
});

importSourceFile?.addEventListener("change", async () => {
  const file = importSourceFile.files?.[0];
  if (!file) {
    return;
  }
  await importMailboxMessageSource(file);
  importSourceFile.value = "";
});

starAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before starring.", "error");
    return;
  }
  await setMailboxMessageStarState(selectedMessageDetail, true);
});

unstarAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before unstarring.", "error");
    return;
  }
  await setMailboxMessageStarState(selectedMessageDetail, false);
});

markReadAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before marking read.", "error");
    return;
  }
  await setMailboxMessageReadState(selectedMessageDetail, true);
});

markUnreadAction?.addEventListener("click", async () => {
  if (!selectedMessageDetail) {
    setStatus("Select a message before marking unread.", "error");
    return;
  }
  await setMailboxMessageReadState(selectedMessageDetail, false);
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

bulkReadAction?.addEventListener("click", async () => bulkMailboxMessages("read", "Bulk messages marked read."));
bulkUnreadAction?.addEventListener("click", async () => bulkMailboxMessages("unread", "Bulk messages marked unread."));
bulkStarAction?.addEventListener("click", async () => bulkMailboxMessages("star", "Bulk messages starred."));
bulkUnstarAction?.addEventListener("click", async () => bulkMailboxMessages("unstar", "Bulk messages unstarred."));
bulkArchiveAction?.addEventListener("click", async () => bulkMailboxMessages("archive", "Bulk messages archived."));
bulkSpamAction?.addEventListener("click", async () => bulkMailboxMessages("spam", "Bulk messages moved to spam."));
bulkDeleteAction?.addEventListener("click", async () => bulkMailboxMessages("delete", "Bulk messages moved to trash."));

contactsAction?.addEventListener("click", async () => {
  await loadMailboxContacts();
});

savedContactForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(savedContactForm);
  await saveMailboxContact({
    email: String(form.get("email") || "").trim(),
    displayName: String(form.get("displayName") || "").trim(),
  });
});

logoutAction?.addEventListener("click", async () => {
  await revokeMailboxSession();
});

adminAuthForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminAuthForm);
  await saveAdminSession({
    apiBaseUrl: String(form.get("apiBaseUrl") || "").trim().replace(/\/+$/, ""),
    adminEmail: String(form.get("adminEmail") || "").trim(),
    adminPassword: String(form.get("adminPassword") || ""),
    adminTotpCode: String(form.get("adminTotpCode") || "").trim(),
    adminToken: String(form.get("adminToken") || ""),
    bootstrapToken: String(form.get("bootstrapToken") || ""),
  });
});

adminLogoutAction?.addEventListener("click", async () => {
  await revokeAdminSession();
});

adminSyncPlanAction?.addEventListener("click", async () => {
  await loadMailCoreSyncPlanStatus();
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
      adminRole: String(form.get("adminRole") || "member"),
    },
    "User invited.",
  );
});

adminMfaSetupAction?.addEventListener("click", async () => {
  await setupAdminTotp();
});

adminMfaForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminMfaForm);
  await verifyAdminTotp(String(form.get("totpCode") || "").trim());
});

adminMfaDisableAction?.addEventListener("click", async () => {
  await disableAdminTotp();
});

adminUserPasswordForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminUserPasswordForm);
  const userId = Number(form.get("userId"));
  await createAdminRecord(
    `/api/v1/admin/users/${userId}/password`,
    { newPassword: String(form.get("newPassword") || "") },
    "User password rotated.",
    "PATCH",
  );
  adminUserPasswordForm.reset();
});

adminMailboxForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminMailboxForm);
  const quotaBytes = Number(form.get("quotaBytes"));
  await createAdminRecord(
    "/api/v1/admin/mailboxes",
    {
      userId: Number(form.get("userId")),
      domainId: Number(form.get("domainId")),
      localPart: String(form.get("localPart") || "").trim(),
      quotaBytes: quotaBytes > 0 ? quotaBytes : null,
    },
    "Mailbox created.",
  );
});

adminMailboxQuotaForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(adminMailboxQuotaForm);
  const mailboxId = Number(form.get("mailboxId"));
  const quotaBytes = Number(form.get("quotaBytes"));
  await createAdminRecord(
    `/api/v1/admin/mailboxes/${mailboxId}/quota`,
    { quotaBytes: quotaBytes > 0 ? quotaBytes : null },
    "Mailbox quota updated.",
    "PATCH",
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
    await loadMailboxPreferences({ quiet: true });
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

async function loadMailboxPreferences({ quiet = false } = {}) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    return;
  }
  try {
    const response = await fetch(new URL("/api/v1/mailbox/preferences", mailboxSession.apiBaseUrl), {
      headers: mailboxHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const preferences = await response.json();
    mailboxPreferences = {
      displayName: preferences.displayName || "",
      signature: preferences.signature || "",
    };
    renderMailboxPreferences();
    if (!quiet) {
      setStatus("Preferences loaded.", "ready");
    }
  } catch (error) {
    if (!quiet) {
      setStatus(`Preference load failed: ${readableError(error)}`, "error");
    }
  }
}

async function saveMailboxPreferences() {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before saving preferences.", "error");
    return;
  }
  const payload = {
    displayName: String(preferenceDisplayName?.value || "").trim(),
    signature: String(preferenceSignature?.value || "").trim(),
  };
  setStatus("Saving preferences...", "loading");
  try {
    const response = await fetch(new URL("/api/v1/mailbox/preferences", mailboxSession.apiBaseUrl), {
      method: "PUT",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const preferences = await response.json();
    mailboxPreferences = {
      displayName: preferences.displayName || "",
      signature: preferences.signature || "",
    };
    renderMailboxPreferences();
    setStatus("Preferences saved.", "ready");
  } catch (error) {
    setStatus(`Preference save failed: ${readableError(error)}`, "error");
  }
}

function renderMailboxPreferences() {
  if (preferenceDisplayName) {
    preferenceDisplayName.value = mailboxPreferences.displayName || "";
  }
  if (preferenceSignature) {
    preferenceSignature.value = mailboxPreferences.signature || "";
  }
}

async function loadMailboxSnapshot(folder, { offset = 0, append = false } = {}) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in to load live mail.", "idle");
    return;
  }
  setStatus(append ? `Loading more ${folder}...` : `Loading ${folder}...`, "loading");
  try {
    const url = new URL("/api/v1/mailbox/snapshot", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", folder);
    url.searchParams.set("limit", String(mailboxPageSize));
    url.searchParams.set("offset", String(offset));
    const response = await fetch(url, {
      headers: mailboxHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const snapshot = await response.json();
    mailboxSession.folder = folder;
    persistMailboxSession(mailboxSession);
    if (!append) {
      selectedMessageIds = new Set();
      clearSearch();
    }
    mailboxPagination = {
      mode: "folder",
      query: "",
      nextOffset: snapshot.nextOffset ?? null,
      hasMore: Boolean(snapshot.hasMore),
    };
    renderFolders(snapshot.folders || [], folder);
    renderMessages(snapshot.messages || [], { append });
    const totalLoaded = visibleMessages.length;
    setStatus(
      `Loaded ${totalLoaded} message${totalLoaded === 1 ? "" : "s"} from ${folder}${mailboxPagination.hasMore ? "." : "."}`,
      "ready",
    );
    loadMailboxContacts({ quiet: true });
  } catch (error) {
    setStatus(`Mailbox load failed: ${readableError(error)}`, "error");
  }
}

async function searchMailboxMessages(query, { offset = 0, append = false } = {}) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in to search mail.", "error");
    return;
  }
  if (!query) {
    await loadMailboxSnapshot(mailboxSession.folder);
    return;
  }
  setStatus(append ? `Loading more matches for "${query}"...` : `Searching ${mailboxSession.folder}...`, "loading");
  try {
    const url = new URL("/api/v1/mailbox/search", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", mailboxSession.folder);
    url.searchParams.set("query", query);
    url.searchParams.set("limit", String(mailboxPageSize));
    url.searchParams.set("offset", String(offset));
    const response = await fetch(url, {
      headers: mailboxHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    if (!append) {
      selectedMessageIds = new Set();
    }
    mailboxPagination = {
      mode: "search",
      query,
      nextOffset: result.nextOffset ?? null,
      hasMore: Boolean(result.hasMore),
    };
    renderMessages(result.messages || [], { append });
    setStatus(`Showing ${visibleMessages.length} matches for "${query}".`, "ready");
  } catch (error) {
    setStatus(`Search failed: ${readableError(error)}`, "error");
  }
}

async function loadMailboxThread(message) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in to load a conversation.", "error");
    return;
  }
  setStatus(`Loading conversation "${message.threadSubject || message.subject || "(no subject)"}"...`, "loading");
  try {
    const url = new URL("/api/v1/mailbox/thread", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", message.folder || mailboxSession.folder);
    url.searchParams.set("thread_id", message.threadId);
    url.searchParams.set("limit", "100");
    const response = await fetch(url, { headers: mailboxHeaders() });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const thread = await response.json();
    selectedMessageIds = new Set();
    mailboxPagination = {
      mode: "folder",
      query: "",
      nextOffset: null,
      hasMore: false,
    };
    renderMessages(thread.messages || []);
    setStatus(`Loaded ${thread.messages?.length || 0} conversation message${thread.messages?.length === 1 ? "" : "s"}.`, "ready");
  } catch (error) {
    setStatus(`Conversation load failed: ${readableError(error)}`, "error");
  }
}

async function loadMoreMailboxMessages() {
  if (!mailboxPagination.hasMore || mailboxPagination.nextOffset === null) {
    return;
  }
  if (mailboxPagination.mode === "search") {
    await searchMailboxMessages(mailboxPagination.query, {
      offset: mailboxPagination.nextOffset,
      append: true,
    });
    return;
  }
  await loadMailboxSnapshot(mailboxSession.folder, {
    offset: mailboxPagination.nextOffset,
    append: true,
  });
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
    renderDraftActions(null);
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
    renderDraftActions(null);
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    setStatus(`Move failed: ${readableError(error)}`, "error");
  }
}

async function setMailboxMessageReadState(message, read) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before changing read state.", "error");
    return;
  }
  setStatus(read ? "Marking message read..." : "Marking message unread...", "loading");
  try {
    const url = new URL("/api/v1/mailbox/message/read-state", mailboxSession.apiBaseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        folder: message.folder,
        messageId: message.messageId,
        read,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    selectedMessageDetail = { ...message, unread: !read };
    setStatus(read ? "Message marked read." : "Message marked unread.", "ready");
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    setStatus(`Read state update failed: ${readableError(error)}`, "error");
  }
}

async function setMailboxMessageStarState(message, starred) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before changing star state.", "error");
    return;
  }
  setStatus(starred ? "Starring message..." : "Unstarring message...", "loading");
  try {
    const url = new URL("/api/v1/mailbox/message/star-state", mailboxSession.apiBaseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        folder: message.folder,
        messageId: message.messageId,
        starred,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    selectedMessageDetail = { ...message, starred };
    setStatus(starred ? "Message starred." : "Message unstarred.", "ready");
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    setStatus(`Star state update failed: ${readableError(error)}`, "error");
  }
}

async function bulkMailboxMessages(action, successMessage, targetFolder = null) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before changing selected messages.", "error");
    return;
  }
  const messageIds = [...selectedMessageIds];
  if (!messageIds.length) {
    setStatus("Select messages before using bulk actions.", "error");
    return;
  }
  setStatus(`Applying ${action} to ${messageIds.length} messages...`, "loading");
  try {
    const url = new URL("/api/v1/mailbox/message/bulk", mailboxSession.apiBaseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        folder: mailboxSession.folder,
        messageIds,
        action,
        targetFolder,
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    selectedMessageIds = new Set();
    selectedMessageDetail = null;
    renderDraftActions(null);
    setStatus(`${successMessage} ${result.succeeded || 0}/${messageIds.length} updated.`, "ready");
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    setStatus(`Bulk action failed: ${readableError(error)}`, "error");
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
    const extractedUrl = new URL("/api/v1/mailbox/contacts", mailboxSession.apiBaseUrl);
    extractedUrl.searchParams.set("folder", mailboxSession.folder || "INBOX");
    extractedUrl.searchParams.set("limit", "100");
    const savedUrl = new URL("/api/v1/mailbox/saved-contacts", mailboxSession.apiBaseUrl);
    const [extractedResponse, savedResponse] = await Promise.all([
      fetch(extractedUrl, { headers: mailboxHeaders() }),
      fetch(savedUrl, { headers: mailboxHeaders() }),
    ]);
    if (!extractedResponse.ok) {
      throw new Error(await extractedResponse.text());
    }
    if (!savedResponse.ok) {
      throw new Error(await savedResponse.text());
    }
    const extracted = await extractedResponse.json();
    const saved = await savedResponse.json();
    renderContacts({
      extracted: extracted.contacts || [],
      saved: saved.contacts || [],
    });
    if (!quiet) {
      setStatus(`Loaded ${saved.contacts?.length || 0} saved and ${extracted.contacts?.length || 0} extracted contacts.`, "ready");
    }
  } catch (error) {
    if (!quiet) {
      setStatus(`Contacts load failed: ${readableError(error)}`, "error");
    }
  }
}

async function saveMailboxContact(contact) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in before saving contacts.", "error");
    return;
  }
  if (!contact.email) {
    setStatus("Enter an email address before saving a contact.", "error");
    return;
  }
  setStatus("Saving contact...", "loading");
  try {
    const response = await fetch(new URL("/api/v1/mailbox/saved-contacts", mailboxSession.apiBaseUrl), {
      method: "PUT",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(contact),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    if (savedContactName) {
      savedContactName.value = "";
    }
    if (savedContactEmail) {
      savedContactEmail.value = "";
    }
    await loadMailboxContacts({ quiet: true });
    setStatus(`Saved ${contact.email}.`, "ready");
  } catch (error) {
    setStatus(`Save contact failed: ${readableError(error)}`, "error");
  }
}

async function deleteMailboxContact(contactId) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in before deleting contacts.", "error");
    return;
  }
  setStatus("Deleting contact...", "loading");
  try {
    const response = await fetch(new URL(`/api/v1/mailbox/saved-contacts/${contactId}`, mailboxSession.apiBaseUrl), {
      method: "DELETE",
      headers: mailboxHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    await loadMailboxContacts({ quiet: true });
    setStatus("Contact deleted.", "ready");
  } catch (error) {
    setStatus(`Delete contact failed: ${readableError(error)}`, "error");
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

async function emptyMailboxFolder(folder) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Sign in before emptying folders.", "error");
    return;
  }
  if (emptyProtectedFolder(folder)) {
    setStatus("This mailbox folder cannot be emptied.", "error");
    return;
  }
  if (!window.confirm(`Permanently delete every message in "${folder}"?`)) {
    return;
  }
  setStatus(`Emptying ${folder}...`, "loading");
  try {
    const result = await mutateMailboxFolderEmpty(folder);
    await loadMailboxSnapshot(folder);
    setStatus(`Emptied ${folder}; deleted ${result.deletedCount || 0} message${result.deletedCount === 1 ? "" : "s"}.`, "ready");
  } catch (error) {
    setStatus(`Empty folder failed: ${readableError(error)}`, "error");
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

async function mutateMailboxFolderEmpty(folder) {
  const response = await fetch(new URL("/api/v1/mailbox/folder/empty", mailboxSession.apiBaseUrl), {
    method: "POST",
    headers: {
      ...mailboxHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder }),
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
    setStatus(
      result.sentFolderSaved
        ? `Sent ${result.messageId || "message"} and saved to ${result.sentFolder || "Sent Items"}.`
        : `Sent ${result.messageId || "message"}, but Sent Items was not updated.`,
      result.sentFolderSaved ? "ready" : "error",
    );
    if (composeAttachments) {
      composeAttachments.value = "";
    }
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    setStatus(`Send failed: ${readableError(error)}`, "error");
  }
}

async function saveMailboxDraft(message) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before saving drafts.", "error");
    return;
  }
  setStatus("Saving draft...", "loading");
  try {
    const url = new URL("/api/v1/mailbox/draft", mailboxSession.apiBaseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...message,
        draftFolder: "Drafts",
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    setStatus(`Draft saved to ${result.draftFolder || "Drafts"}.`, "ready");
    await loadMailboxSnapshot(mailboxSession.folder);
  } catch (error) {
    setStatus(`Draft save failed: ${readableError(error)}`, "error");
  }
}

function renderContacts({ extracted = [], saved = [] } = {}) {
  if (!contactsList) {
    return;
  }
  if (!extracted.length && !saved.length) {
    contactsList.replaceChildren(emptyContactsMessage());
    return;
  }
  const savedRows = saved.slice(0, 12).map(savedContactRow);
  const extractedRows = extracted.slice(0, 12).map(extractedContactRow);
  contactsList.replaceChildren(...savedRows, ...extractedRows);
}

function savedContactRow(contact) {
  const row = document.createElement("div");
  row.className = "contact-item saved-contact";
  row.innerHTML = `
    <span>${escapeHtml(contact.displayName || contact.contactEmail)}</span>
    <small>${escapeHtml(contact.contactEmail)} - saved</small>
  `;
  row.addEventListener("click", () => {
    addComposeRecipient(contact.contactEmail);
    setStatus(`Added ${contact.contactEmail} to compose.`, "ready");
  });
  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.textContent = "Delete";
  deleteButton.addEventListener("click", (event) => {
    event.stopPropagation();
    deleteMailboxContact(contact.id);
  });
  row.append(deleteButton);
  return row;
}

function extractedContactRow(contact) {
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

function renderMessages(messages, { append = false } = {}) {
  if (!messageList) {
    return;
  }
  visibleMessages = append ? [...visibleMessages, ...messages] : messages;
  if (!visibleMessages.length) {
    selectedMessageDetail = null;
    selectedMessageIds = new Set();
    replaceMessageListChildren(emptyMessage());
    readerSubject.textContent = "No messages";
    readerMeta.textContent = "Select another folder or refresh the mailbox.";
    renderMessageBody("This folder is empty.");
    renderMessageHeaders(null);
    renderMessageAttachments(null);
    renderDraftActions(null);
    return;
  }
  const rows = visibleMessages.map((message, index) => messageRow(message, !append && index === 0));
  replaceMessageListChildren(...rows);
  if (!append) {
    selectMessage(visibleMessages[0], rows[0]);
  }
}

function replaceMessageListChildren(...children) {
  const paginationToolbar = loadMoreAction?.parentElement || null;
  if (loadMoreAction) {
    loadMoreAction.hidden = !mailboxPagination.hasMore;
    loadMoreAction.textContent = mailboxPagination.mode === "search" ? "Load more matches" : "Load more";
  }
  if (bulkToolbar) {
    messageList.replaceChildren(...[bulkToolbar, ...children, paginationToolbar].filter(Boolean));
    return;
  }
  messageList.replaceChildren(...[...children, paginationToolbar].filter(Boolean));
}

function messageRow(message, selected) {
  const row = document.createElement("article");
  row.className = `message-row${selected ? " selected" : ""}${message.unread ? " unread" : ""}`;
  row.tabIndex = 0;
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "message-select";
  checkbox.checked = selectedMessageIds.has(message.messageId);
  checkbox.setAttribute("aria-label", `Select ${message.subject || "message"}`);
  checkbox.addEventListener("click", (event) => {
    event.stopPropagation();
  });
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) {
      selectedMessageIds.add(message.messageId);
    } else {
      selectedMessageIds.delete(message.messageId);
    }
  });
  const content = document.createElement("div");
  content.className = "message-row-content";
  row.innerHTML = `
    <span class="sender">${escapeHtml(message.sender || "Unknown sender")}</span>
    <strong>${escapeHtml(message.starred ? `* ${message.subject || "(no subject)"}` : message.subject || "(no subject)")}</strong>
    ${threadHint(message)}
    <p>${escapeHtml(message.recipients || "")}</p>
    <time>${escapeHtml(shortDate(message.date))}</time>
  `;
  content.append(...Array.from(row.childNodes));
  row.replaceChildren(checkbox, content);
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
  readerMeta.textContent = readerMetadata(message);
  renderMessageBody("Loading message...");
  renderMessageHeaders(null);
  try {
    const detail = await loadMailboxMessage(message.folder, message.messageId);
    selectedMessageDetail = detail;
    readerSubject.textContent = detail.subject || "(no subject)";
    readerMeta.textContent = readerMetadata(detail);
    renderMessageBody(detail.body || "(No plain text body)");
    renderMessageAttachments(detail);
    renderDraftActions(detail);
  } catch (error) {
    selectedMessageDetail = null;
    renderMessageBody(`Message load failed: ${readableError(error)}`);
    renderMessageHeaders(null);
    renderMessageAttachments(null);
    renderDraftActions(null);
  }
}

function threadHint(message) {
  if (!message.threadId) {
    return "";
  }
  const subject = message.subject || "(no subject)";
  const threadSubject = message.threadSubject || subject;
  if (!message.inReplyTo && threadSubject === subject) {
    return "";
  }
  return `<small class="thread-hint">Thread: ${escapeHtml(threadSubject)}</small>`;
}

function readerMetadata(message) {
  const base = `From ${message.sender || "Unknown sender"} to ${message.recipients || mailboxSession.email}`;
  if (!message.threadId) {
    return base;
  }
  return `${base} | Thread ${message.threadSubject || message.subject || "(no subject)"}`;
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
  if (folderEmptyAction) {
    folderEmptyAction.disabled = emptyProtectedFolder(activeFolder);
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

function emptyProtectedFolder(folder) {
  return emptyProtectedFolders.includes(String(folder || "").trim().toLowerCase());
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
    composeBody.value = withSignature(body);
    composeBody.focus();
  }
}

function prefillSavedDraft(message) {
  fillCompose({
    to: draftRecipients(message),
    subject: message.subject === "(no subject)" ? "" : message.subject || "",
    body: message.body || "",
  });
  if (composeAttachments) {
    composeAttachments.value = "";
  }
  const attachmentNote = message.attachments?.length ? " Reattach files before saving or sending." : "";
  setStatus(`Draft loaded into compose.${attachmentNote}`, "ready");
}

function renderDraftActions(message) {
  if (editDraftAction) {
    editDraftAction.hidden = !isDraftMessage(message);
  }
}

function isDraftMessage(message) {
  return String(message?.folder || "").trim().toLowerCase() === "drafts";
}

function draftRecipients(message) {
  return String(message?.recipients || "")
    .split(",")
    .map((recipient) => recipient.trim())
    .filter(Boolean)
    .join(", ");
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

async function loadMailboxMessageHeaders(message) {
  setStatus("Loading message headers...", "loading");
  try {
    const url = new URL("/api/v1/mailbox/message/headers", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", message.folder);
    url.searchParams.set("message_id", message.messageId);
    const response = await fetch(url, {
      headers: mailboxHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    renderMessageHeaders(await response.json());
    setStatus("Message headers loaded.", "ready");
  } catch (error) {
    setStatus(`Header load failed: ${readableError(error)}`, "error");
  }
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

async function downloadMailboxMessageSource(message) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before downloading EML.", "error");
    return;
  }
  setStatus("Downloading message EML...", "loading");
  try {
    const url = new URL("/api/v1/mailbox/message/source", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", message.folder);
    url.searchParams.set("message_id", message.messageId);
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
    link.download = `freemail-${safeDownloadName(message.folder)}-${safeDownloadName(message.messageId)}.eml`;
    link.click();
    URL.revokeObjectURL(href);
    setStatus("Downloaded message EML.", "ready");
  } catch (error) {
    setStatus(`EML download failed: ${readableError(error)}`, "error");
  }
}

async function importMailboxMessageSource(file) {
  if (!mailboxSession.token || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before importing EML.", "error");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".eml") && file.type !== "message/rfc822") {
    setStatus("Choose an .eml message source file.", "error");
    return;
  }
  setStatus(`Importing ${file.name} into ${mailboxSession.folder}...`, "loading");
  try {
    const response = await fetch(new URL("/api/v1/mailbox/message/import", mailboxSession.apiBaseUrl), {
      method: "POST",
      headers: {
        ...mailboxHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        folder: mailboxSession.folder,
        filename: safeDownloadName(file.name),
        contentBase64: await fileToBase64(file),
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const imported = await response.json();
    await loadMailboxSnapshot(mailboxSession.folder);
    setStatus(`Imported ${imported.filename || file.name} into ${imported.folder || mailboxSession.folder}.`, "ready");
  } catch (error) {
    setStatus(`EML import failed: ${readableError(error)}`, "error");
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

function renderMessageHeaders(headers) {
  if (!messageHeaders) {
    return;
  }
  if (!headers) {
    messageHeaders.replaceChildren();
    return;
  }
  const heading = document.createElement("h3");
  heading.textContent = "Headers";
  const summary = document.createElement("dl");
  summary.className = "header-summary";
  const entries = [
    ["From", headers.sender],
    ["To", headers.recipients],
    ["Reply-To", headers.replyTo],
    ["Message-ID", headers.messageIdHeader],
    ["Authentication", (headers.authenticationResults || []).join(" | ")],
    ["List-Unsubscribe", headers.listUnsubscribe],
    ["Received hops", String(headers.receivedCount || 0)],
  ].filter(([, value]) => value);
  entries.forEach(([name, value]) => {
    const term = document.createElement("dt");
    term.textContent = name;
    const detail = document.createElement("dd");
    detail.textContent = value;
    summary.append(term, detail);
  });
  const details = document.createElement("details");
  const label = document.createElement("summary");
  label.textContent = `All headers (${(headers.headers || []).length})`;
  const list = document.createElement("dl");
  list.className = "header-list";
  (headers.headers || []).forEach((header) => {
    const term = document.createElement("dt");
    term.textContent = header.name;
    const detail = document.createElement("dd");
    detail.textContent = header.value;
    list.append(term, detail);
  });
  details.append(label, list);
  messageHeaders.replaceChildren(heading, summary, details);
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

function safeDownloadName(value) {
  return String(value || "message").replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 96) || "message";
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
    loadMailboxPreferences({ quiet: true });
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
  mailboxPreferences = { displayName: "", signature: "" };
  selectedMessageDetail = null;
  selectedMessageIds = new Set();
  renderMailboxPreferences();
  renderDraftActions(null);
  clearSearch();
}

async function saveAdminSession({ apiBaseUrl, adminEmail, adminPassword, adminTotpCode, adminToken, bootstrapToken }) {
  if (!apiBaseUrl) {
    setAdminStatus("Enter an API URL before saving admin access.", "error");
    return;
  }
  adminSession = {
    apiBaseUrl,
    adminToken,
    adminBearerToken: "",
    adminEmail,
    bootstrapToken,
  };
  if (adminEmail || adminPassword) {
    if (!adminEmail || !adminPassword) {
      setAdminStatus("Enter both admin email and password to sign in.", "error");
      return;
    }
    setAdminStatus("Signing in as administrator...", "loading");
    try {
      const response = await fetch(new URL("/api/v1/admin/session", apiBaseUrl), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: adminEmail, password: adminPassword, totpCode: adminTotpCode || null }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const session = await response.json();
      adminSession.adminBearerToken = session.token;
      adminSession.adminEmail = session.email || adminEmail;
      if (adminPasswordInput) {
        adminPasswordInput.value = "";
      }
      if (adminTotpCodeInput) {
        adminTotpCodeInput.value = "";
      }
    } catch (error) {
      forgetAdminSession();
      setAdminStatus(`Admin sign in failed: ${readableError(error)}`, "error");
      return;
    }
  }
  persistAdminSession(adminSession);
  setAdminStatus(hasAdminCredential() ? "Admin session saved in this browser profile." : "Admin settings saved.", "ready");
}

async function setupAdminTotp() {
  if (!adminSession.apiBaseUrl || !hasAdminCredential()) {
    setAdminStatus("Save an admin login session before setting up MFA.", "error");
    return;
  }
  setAdminStatus("Generating authenticator setup...", "loading");
  try {
    const response = await fetch(new URL("/api/v1/admin/mfa/totp/setup", adminSession.apiBaseUrl), {
      method: "POST",
      headers: adminHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderAdminResult("Admin MFA setup", {
      secret: result.secret,
      otpauthUri: result.otpauthUri,
      enabled: result.enabled,
    });
    setAdminStatus("Authenticator setup generated. Add it to your app, then enter a code to enable MFA.", "ready");
  } catch (error) {
    setAdminStatus(`MFA setup failed: ${readableError(error)}`, "error");
  }
}

async function verifyAdminTotp(code) {
  if (!adminSession.apiBaseUrl || !hasAdminCredential()) {
    setAdminStatus("Save an admin login session before enabling MFA.", "error");
    return;
  }
  setAdminStatus("Verifying authenticator code...", "loading");
  try {
    const response = await fetch(new URL("/api/v1/admin/mfa/totp/verify", adminSession.apiBaseUrl), {
      method: "POST",
      headers: adminHeaders(),
      body: JSON.stringify({ code }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderAdminResult("Admin MFA enabled", result);
    setAdminStatus("Admin MFA enabled.", "ready");
    adminMfaForm?.reset();
  } catch (error) {
    setAdminStatus(`MFA verification failed: ${readableError(error)}`, "error");
  }
}

async function disableAdminTotp() {
  if (!adminSession.apiBaseUrl || !hasAdminCredential()) {
    setAdminStatus("Save an admin login session before disabling MFA.", "error");
    return;
  }
  setAdminStatus("Disabling admin MFA...", "loading");
  try {
    const response = await fetch(new URL("/api/v1/admin/mfa/totp", adminSession.apiBaseUrl), {
      method: "DELETE",
      headers: adminHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderAdminResult("Admin MFA disabled", result);
    setAdminStatus("Admin MFA disabled.", "ready");
  } catch (error) {
    setAdminStatus(`MFA disable failed: ${readableError(error)}`, "error");
  }
}

async function revokeAdminSession() {
  const token = adminSession.adminBearerToken;
  const apiBaseUrl = adminSession.apiBaseUrl;
  forgetAdminSession();
  if (token && apiBaseUrl) {
    try {
      await fetch(new URL("/api/v1/admin/session", apiBaseUrl), {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (_error) {
      // Local cleanup is enough for this browser; server expiry cleans stale sessions.
    }
  }
  setAdminStatus("Admin signed out.", "idle");
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

async function createAdminRecord(path, payload, successMessage, method = "POST") {
  if (!adminSession.apiBaseUrl || !hasAdminCredential()) {
    setAdminStatus("Save an admin login session or admin token before making admin changes.", "error");
    return;
  }
  setAdminStatus("Saving admin change...", "loading");
  try {
    const response = await fetch(new URL(path, adminSession.apiBaseUrl), {
      method,
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
  if (!adminSession.apiBaseUrl || !hasAdminCredential()) {
    setAdminStatus("Save an admin login session or admin token before loading admin metadata.", "error");
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
  const headers = { "Content-Type": "application/json" };
  if (adminSession.adminBearerToken) {
    headers.Authorization = `Bearer ${adminSession.adminBearerToken}`;
  } else {
    headers["X-FreeMail-Admin-Token"] = adminSession.adminToken;
  }
  return headers;
}

function hasAdminCredential() {
  return Boolean(adminSession.adminBearerToken || adminSession.adminToken);
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
    adminTable("Users", users, ["id", "email", "displayName", "isAdmin", "adminRole", "status"], {
      statusPath: "/api/v1/admin/users",
      statusActiveValue: "invited",
    }),
    adminTable("Mailboxes", mailboxes, ["id", "address", "userId", "quotaBytes", "status"], {
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
  if (!adminSession.apiBaseUrl || !hasAdminCredential()) {
    setAdminStatus("Save an admin login session or admin token before changing status.", "error");
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
  if (!adminSession.apiBaseUrl || !hasAdminCredential()) {
    setAdminStatus("Save an admin login session or admin token before loading DNS guidance.", "error");
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

async function loadMailCoreSyncPlanStatus() {
  if (!adminSession.apiBaseUrl || !hasAdminCredential()) {
    setAdminStatus("Save an admin login session or admin token before loading sync status.", "error");
    return;
  }
  setAdminStatus("Loading mail-core sync status...", "loading");
  try {
    const response = await fetch(new URL("/api/v1/admin/mail-core/sync-plan/status", adminSession.apiBaseUrl), {
      method: "POST",
      headers: adminHeaders(),
      body: JSON.stringify({ availableUserSecrets: [] }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    renderAdminResult("Mail-core sync status", result);
    setAdminStatus(result.ready ? "Mail-core sync plan is ready." : "Mail-core sync plan needs account secrets.", "ready");
  } catch (error) {
    setAdminStatus(`Mail-core sync status failed: ${readableError(error)}`, "error");
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
      adminBearerToken: String(stored.adminBearerToken || ""),
      adminEmail: String(stored.adminEmail || ""),
      bootstrapToken: String(stored.bootstrapToken || ""),
    };
    if (adminApiBaseUrl) {
      adminApiBaseUrl.value = adminSession.apiBaseUrl;
    }
    if (adminEmailInput) {
      adminEmailInput.value = adminSession.adminEmail;
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
      adminBearerToken: session.adminBearerToken,
      adminEmail: session.adminEmail,
      bootstrapToken: session.bootstrapToken,
    }),
  );
}

function forgetAdminSession() {
  window.localStorage.removeItem(adminSessionStorageKey);
  adminSession = { apiBaseUrl: "", adminToken: "", adminBearerToken: "", adminEmail: "", bootstrapToken: "" };
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

async function composePayload() {
  const form = new FormData(composeForm);
  return {
    recipients: String(form.get("to") || "")
      .split(",")
      .map((recipient) => recipient.trim())
      .filter(Boolean),
    subject: String(form.get("subject") || "").trim(),
    body: withSignature(String(form.get("body") || "")),
    attachments: await filesToAttachments(composeAttachments?.files || []),
  };
}

function withSignature(body) {
  const signature = String(mailboxPreferences.signature || "").trim();
  const current = String(body || "");
  if (!signature || current.includes(signature)) {
    return current;
  }
  const separator = current.trim() ? "\n\n-- \n" : "-- \n";
  return `${current}${separator}${signature}`;
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
