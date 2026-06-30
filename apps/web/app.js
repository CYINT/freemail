const loginForm = document.querySelector("#mailbox-login");
const folderNav = document.querySelector("#folder-nav");
const messageList = document.querySelector("#message-list");
const statusNode = document.querySelector("#mailbox-status");
const readerSubject = document.querySelector("#reader-subject");
const readerMeta = document.querySelector("#reader-meta");
const messageBody = document.querySelector("#message-body");
const composeForm = document.querySelector("#compose-form");

let mailboxSession = {
  email: "",
  password: "",
  apiBaseUrl: "",
  folder: "INBOX",
};

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(loginForm);
  mailboxSession = {
    email: String(form.get("email") || "").trim(),
    password: String(form.get("password") || ""),
    apiBaseUrl: String(form.get("apiBaseUrl") || "").trim().replace(/\/+$/, ""),
    folder: mailboxSession.folder || "INBOX",
  };
  await loadMailboxSnapshot(mailboxSession.folder);
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
  });
});

async function loadMailboxSnapshot(folder) {
  if (!mailboxSession.email || !mailboxSession.password || !mailboxSession.apiBaseUrl) {
    setStatus("Enter mailbox credentials to load live mail.", "idle");
    return;
  }
  setStatus(`Loading ${folder}...`, "loading");
  try {
    const url = new URL("/api/v1/mailbox/snapshot", mailboxSession.apiBaseUrl);
    url.searchParams.set("folder", folder);
    url.searchParams.set("limit", "25");
    const response = await fetch(url, {
      headers: {
        "X-FreeMail-Mailbox-Email": mailboxSession.email,
        "X-FreeMail-Mailbox-Password": mailboxSession.password,
      },
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const snapshot = await response.json();
    mailboxSession.folder = folder;
    renderFolders(snapshot.folders || [], folder);
    renderMessages(snapshot.messages || []);
    setStatus(`Loaded ${snapshot.messages?.length || 0} messages from ${folder}.`, "ready");
  } catch (error) {
    setStatus(`Mailbox load failed: ${readableError(error)}`, "error");
  }
}

async function sendMailboxMessage(message) {
  if (!mailboxSession.email || !mailboxSession.password || !mailboxSession.apiBaseUrl) {
    setStatus("Load a mailbox before sending.", "error");
    return;
  }
  setStatus("Sending message...", "loading");
  try {
    const url = new URL("/api/v1/mailbox/send", mailboxSession.apiBaseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-FreeMail-Mailbox-Email": mailboxSession.email,
        "X-FreeMail-Mailbox-Password": mailboxSession.password,
      },
      body: JSON.stringify(message),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    setStatus(`Sent ${result.messageId || "message"}.`, "ready");
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
    messageList.replaceChildren(emptyMessage());
    readerSubject.textContent = "No messages";
    readerMeta.textContent = "Select another folder or refresh the mailbox.";
    renderMessageBody("This folder is empty.");
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
    readerSubject.textContent = detail.subject || "(no subject)";
    readerMeta.textContent = `From ${detail.sender || "Unknown sender"} to ${detail.recipients || mailboxSession.email}`;
    renderMessageBody(detail.body || "(No plain text body)");
  } catch (error) {
    renderMessageBody(`Message load failed: ${readableError(error)}`);
  }
}

async function loadMailboxMessage(folder, messageId) {
  const url = new URL("/api/v1/mailbox/message", mailboxSession.apiBaseUrl);
  url.searchParams.set("folder", folder);
  url.searchParams.set("message_id", messageId);
  const response = await fetch(url, {
    headers: {
      "X-FreeMail-Mailbox-Email": mailboxSession.email,
      "X-FreeMail-Mailbox-Password": mailboxSession.password,
    },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
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
