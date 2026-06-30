import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  createMailboxFolder,
  createMailboxSession,
  deleteMailboxFolder,
  loadMailboxAttachment,
  loadMailboxContacts,
  loadMailboxMessage,
  loadMailboxSnapshot,
  MailboxSession,
  MailContact,
  MailFolder,
  MailMessage,
  MailMessageDetail,
  renameMailboxFolder,
  revokeMailboxSession,
  searchMailbox,
  sendMailboxMessage,
} from "./src/api";
import { clearCachedMailboxSnapshots, loadCachedMailboxSnapshot, saveCachedMailboxSnapshot } from "./src/offlineCache";
import { clearStoredMailboxSession, loadStoredMailboxSession, saveMailboxSession } from "./src/sessionStore";

const defaultApiBaseUrl = "https://freemail.kuzuryu.ai";
const protectedFolders = new Set(["INBOX", "Archive", "Deleted Items", "Junk Mail", "Sent Items", "Drafts"]);

export default function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(defaultApiBaseUrl);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [session, setSession] = useState<MailboxSession | null>(null);
  const [folder, setFolder] = useState("INBOX");
  const [folders, setFolders] = useState<MailFolder[]>([]);
  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [contacts, setContacts] = useState<MailContact[]>([]);
  const [selectedMessage, setSelectedMessage] = useState<MailMessageDetail | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [newFolderName, setNewFolderName] = useState("");
  const [renameFolderName, setRenameFolderName] = useState("");
  const [composeTo, setComposeTo] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [status, setStatus] = useState("VPN-only FreeMail mobile preview");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadStoredMailboxSession().then((stored) => {
      if (stored) {
        setSession(stored);
        setApiBaseUrl(stored.apiBaseUrl);
        setEmail(stored.email);
        refreshMailbox(stored, "INBOX");
      }
    });
  }, []);

  const selectedSubject = useMemo(() => selectedMessage?.subject || "Select a message", [selectedMessage]);
  const canMutateFolder = !protectedFolders.has(folder);

  async function signIn() {
    setLoading(true);
    setStatus("Starting session...");
    try {
      const created = await createMailboxSession(apiBaseUrl, email.trim(), password);
      await saveMailboxSession(created);
      setSession(created);
      setPassword("");
      await refreshMailbox(created, "INBOX");
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function signOut() {
    const activeSession = session;
    setSession(null);
    setFolders([]);
    setMessages([]);
    setContacts([]);
    setSelectedMessage(null);
    await clearStoredMailboxSession();
    if (activeSession) {
      await clearCachedMailboxSnapshots(activeSession.email).catch(() => undefined);
    }
    if (activeSession) {
      await revokeMailboxSession(activeSession).catch(() => undefined);
    }
    setStatus("Signed out.");
  }

  async function refreshMailbox(activeSession = session, targetFolder = folder) {
    if (!activeSession) {
      return;
    }
    setLoading(true);
    setStatus(`Loading ${targetFolder}...`);
    try {
      const cached = await loadCachedMailboxSnapshot(activeSession, targetFolder);
      if (cached) {
        setFolder(cached.folder);
        setFolders(cached.folders);
        setMessages(cached.messages);
        setContacts(cached.contacts);
        setStatus(`Showing cached ${cached.folder} from ${formatCachedAt(cached.cachedAt)}.`);
      }
      const [snapshot, contactList] = await Promise.all([
        loadMailboxSnapshot(activeSession, targetFolder),
        loadMailboxContacts(activeSession, targetFolder),
      ]);
      setFolder(targetFolder);
      setFolders(snapshot.folders || []);
      setMessages(snapshot.messages || []);
      setContacts(contactList.contacts || []);
      setSelectedMessage(null);
      await saveCachedMailboxSnapshot(activeSession, targetFolder, snapshot, contactList.contacts || []);
      setStatus(`Loaded ${snapshot.messages?.length || 0} messages from ${targetFolder}.`);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function runSearch() {
    if (!session) {
      return;
    }
    const query = searchQuery.trim();
    if (!query) {
      await refreshMailbox(session, folder);
      return;
    }
    setLoading(true);
    setStatus("Searching mailbox...");
    try {
      const result = await searchMailbox(session, folder, query);
      setMessages(result.messages || []);
      setSelectedMessage(null);
      setStatus(`Found ${result.messages?.length || 0} messages in ${folder}.`);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function openMessage(message: MailMessage) {
    if (!session) {
      return;
    }
    setLoading(true);
    setStatus("Loading message...");
    try {
      const detail = await loadMailboxMessage(session, message.folder, message.messageId);
      setSelectedMessage(detail);
      setStatus("Message loaded.");
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function sendDraft() {
    if (!session) {
      return;
    }
    setLoading(true);
    setStatus("Sending message...");
    try {
      await sendMailboxMessage(session, {
        recipients: composeTo
          .split(",")
          .map((recipient) => recipient.trim())
          .filter(Boolean),
        subject: composeSubject.trim(),
        body: composeBody,
      });
      setComposeTo("");
      setComposeSubject("");
      setComposeBody("");
      setStatus("Message sent.");
      await refreshMailbox(session, folder);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function addFolder() {
    if (!session || !newFolderName.trim()) {
      return;
    }
    setLoading(true);
    try {
      const target = newFolderName.trim();
      await createMailboxFolder(session, target);
      setNewFolderName("");
      await refreshMailbox(session, target);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function renameCurrentFolder() {
    if (!session || !renameFolderName.trim() || !canMutateFolder) {
      return;
    }
    setLoading(true);
    try {
      const target = renameFolderName.trim();
      await renameMailboxFolder(session, folder, target);
      setRenameFolderName("");
      await refreshMailbox(session, target);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function deleteCurrentFolder() {
    if (!session || !canMutateFolder) {
      return;
    }
    setLoading(true);
    try {
      await deleteMailboxFolder(session, folder);
      await refreshMailbox(session, "INBOX");
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  function replyToSelectedMessage() {
    if (!selectedMessage) {
      return;
    }
    setComposeTo(selectedMessage.sender);
    setComposeSubject(prefixedSubject("Re:", selectedMessage.subject));
    setComposeBody(`\n\nOn ${selectedMessage.date}, ${selectedMessage.sender} wrote:\n${quoteBody(selectedMessage.body)}`);
  }

  function forwardSelectedMessage() {
    if (!selectedMessage) {
      return;
    }
    setComposeTo("");
    setComposeSubject(prefixedSubject("Fwd:", selectedMessage.subject));
    setComposeBody(`\n\nForwarded message\nFrom: ${selectedMessage.sender}\nTo: ${selectedMessage.recipients}\n\n${selectedMessage.body}`);
  }

  async function inspectAttachment(attachmentId: string, filename: string) {
    if (!session || !selectedMessage) {
      return;
    }
    setLoading(true);
    setStatus(`Checking attachment ${filename}...`);
    try {
      const blob = await loadMailboxAttachment(session, selectedMessage.folder, selectedMessage.messageId, attachmentId);
      setStatus(`Attachment available: ${filename} (${blob.size} bytes).`);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  function addContactToDraft(contact: MailContact) {
    const existing = composeTo
      .split(",")
      .map((recipient) => recipient.trim())
      .filter(Boolean);
    if (!existing.includes(contact.email)) {
      setComposeTo([...existing, contact.email].join(", "));
    }
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <KeyboardAvoidingView behavior={Platform.select({ ios: "padding", android: undefined })} style={styles.container}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>VPN-only mobile client</Text>
            <Text style={styles.title}>FreeMail</Text>
          </View>
          {session ? (
            <Pressable style={styles.secondaryButton} onPress={signOut}>
              <Text>Sign out</Text>
            </Pressable>
          ) : null}
        </View>

        {!session ? (
          <View style={styles.panel}>
            <TextInput value={apiBaseUrl} onChangeText={setApiBaseUrl} style={styles.input} autoCapitalize="none" />
            <TextInput value={email} onChangeText={setEmail} style={styles.input} autoCapitalize="none" placeholder="Mailbox email" />
            <TextInput value={password} onChangeText={setPassword} style={styles.input} placeholder="Mailbox password" secureTextEntry />
            <Pressable style={styles.primaryButton} onPress={signIn}>
              <Text style={styles.primaryButtonText}>Start session</Text>
            </Pressable>
          </View>
        ) : (
          <ScrollView style={styles.workspace} contentContainerStyle={styles.workspaceContent}>
            <View style={styles.panel}>
              <View style={styles.rowHeader}>
                <Text style={styles.sectionTitle}>{folder}</Text>
                <Pressable style={styles.secondaryButton} onPress={() => refreshMailbox()}>
                  <Text>Refresh</Text>
                </Pressable>
              </View>
              <FlatList
                horizontal
                data={folders}
                keyExtractor={(item) => item.name}
                renderItem={({ item }) => (
                  <Pressable style={[styles.folderChip, item.name === folder ? styles.activeFolderChip : null]} onPress={() => refreshMailbox(session, item.name)}>
                    <Text style={item.name === folder ? styles.activeFolderText : styles.folderText}>{item.name}</Text>
                    <Text style={styles.folderCount}>{item.unreadCount}/{item.messageCount}</Text>
                  </Pressable>
                )}
                showsHorizontalScrollIndicator={false}
              />
              <View style={styles.inlineControls}>
                <TextInput value={searchQuery} onChangeText={setSearchQuery} style={[styles.input, styles.flexInput]} placeholder="Search mail" />
                <Pressable style={styles.secondaryButton} onPress={runSearch}>
                  <Text>Search</Text>
                </Pressable>
              </View>
            </View>

            <View style={styles.panel}>
              <Text style={styles.sectionTitle}>Folders</Text>
              <View style={styles.inlineControls}>
                <TextInput value={newFolderName} onChangeText={setNewFolderName} style={[styles.input, styles.flexInput]} placeholder="New folder" />
                <Pressable style={styles.secondaryButton} onPress={addFolder}>
                  <Text>Add</Text>
                </Pressable>
              </View>
              <View style={styles.inlineControls}>
                <TextInput
                  value={renameFolderName}
                  onChangeText={setRenameFolderName}
                  style={[styles.input, styles.flexInput]}
                  placeholder="Rename current folder"
                  editable={canMutateFolder}
                />
                <Pressable style={[styles.secondaryButton, !canMutateFolder ? styles.disabledButton : null]} onPress={renameCurrentFolder}>
                  <Text>Rename</Text>
                </Pressable>
                <Pressable style={[styles.dangerButton, !canMutateFolder ? styles.disabledButton : null]} onPress={deleteCurrentFolder}>
                  <Text style={styles.dangerButtonText}>Delete</Text>
                </Pressable>
              </View>
            </View>

            <View style={styles.listPanel}>
              <FlatList
                data={messages}
                scrollEnabled={false}
                keyExtractor={(item) => `${item.folder}:${item.messageId}`}
                renderItem={({ item }) => (
                  <Pressable style={styles.messageRow} onPress={() => openMessage(item)}>
                    <Text style={styles.sender}>{item.sender || "Unknown sender"}</Text>
                    <Text style={styles.subject}>{item.subject || "(no subject)"}</Text>
                    <Text style={styles.meta}>{item.recipients}</Text>
                  </Pressable>
                )}
              />
            </View>

            <View style={styles.readerPanel}>
              <Text style={styles.sectionTitle}>{selectedSubject}</Text>
              <Text style={styles.meta}>{selectedMessage ? `From ${selectedMessage.sender}` : "Open a message to read it."}</Text>
              <Text style={styles.body}>{selectedMessage?.body || ""}</Text>
              {selectedMessage ? (
                <View style={styles.inlineControls}>
                  <Pressable style={styles.secondaryButton} onPress={replyToSelectedMessage}>
                    <Text>Reply</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={forwardSelectedMessage}>
                    <Text>Forward</Text>
                  </Pressable>
                </View>
              ) : null}
              {selectedMessage?.attachments?.map((attachment) => (
                <Pressable
                  key={attachment.attachmentId}
                  style={styles.attachmentRow}
                  onPress={() => inspectAttachment(attachment.attachmentId, attachment.filename)}
                >
                  <Text style={styles.subject}>{attachment.filename}</Text>
                  <Text style={styles.meta}>
                    {attachment.contentType} - {attachment.size} bytes
                  </Text>
                </Pressable>
              ))}
            </View>

            <View style={styles.panel}>
              <Text style={styles.sectionTitle}>Contacts</Text>
              {contacts.slice(0, 8).map((contact) => (
                <Pressable key={contact.email} style={styles.contactRow} onPress={() => addContactToDraft(contact)}>
                  <Text style={styles.sender}>{contact.name || contact.email}</Text>
                  <Text style={styles.meta}>
                    {contact.email} - {contact.messageCount} messages
                  </Text>
                </Pressable>
              ))}
            </View>

            <View style={styles.panel}>
              <Text style={styles.sectionTitle}>Compose</Text>
              <TextInput value={composeTo} onChangeText={setComposeTo} style={styles.input} autoCapitalize="none" placeholder="To" />
              <TextInput value={composeSubject} onChangeText={setComposeSubject} style={styles.input} placeholder="Subject" />
              <TextInput value={composeBody} onChangeText={setComposeBody} style={[styles.input, styles.composeBody]} multiline placeholder="Message" />
              <Pressable style={styles.primaryButton} onPress={sendDraft}>
                <Text style={styles.primaryButtonText}>Send</Text>
              </Pressable>
            </View>
          </ScrollView>
        )}

        <View style={styles.statusBar}>
          {loading ? <ActivityIndicator /> : null}
          <Text style={styles.statusText}>{status}</Text>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function readableError(error: unknown): string {
  return error instanceof Error ? error.message.slice(0, 180) : "Request failed.";
}

function prefixedSubject(prefix: string, subject: string): string {
  return subject.startsWith(prefix) ? subject : `${prefix} ${subject || "(no subject)"}`;
}

function quoteBody(body: string): string {
  return body
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n");
}

function formatCachedAt(cachedAt: string): string {
  if (!cachedAt) {
    return "offline cache";
  }
  return new Date(cachedAt).toLocaleString();
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f5f7fb" },
  container: { flex: 1, padding: 16, gap: 12 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  eyebrow: { color: "#5c667a", fontSize: 12, textTransform: "uppercase" },
  title: { color: "#162032", fontSize: 28, fontWeight: "700" },
  panel: { backgroundColor: "#ffffff", borderRadius: 8, padding: 12, gap: 10 },
  workspace: { flex: 1 },
  workspaceContent: { gap: 12, paddingBottom: 12 },
  listPanel: { backgroundColor: "#ffffff", borderRadius: 8, padding: 12, minHeight: 220 },
  readerPanel: { backgroundColor: "#ffffff", borderRadius: 8, padding: 12, minHeight: 140, gap: 10 },
  rowHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  inlineControls: { flexDirection: "row", alignItems: "center", gap: 8 },
  flexInput: { flex: 1 },
  sectionTitle: { color: "#1c2638", fontSize: 18, fontWeight: "700" },
  folderChip: {
    borderColor: "#cbd5e1",
    borderRadius: 8,
    borderWidth: 1,
    marginRight: 8,
    minWidth: 96,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  activeFolderChip: { backgroundColor: "#176b5f", borderColor: "#176b5f" },
  folderText: { color: "#1f2937", fontWeight: "700" },
  activeFolderText: { color: "#ffffff", fontWeight: "700" },
  folderCount: { color: "#697386", fontSize: 12, marginTop: 2 },
  messageRow: { borderBottomColor: "#d8dee9", borderBottomWidth: 1, paddingVertical: 10, gap: 3 },
  contactRow: { borderBottomColor: "#eef2f7", borderBottomWidth: 1, paddingVertical: 8, gap: 2 },
  attachmentRow: { borderColor: "#cbd5e1", borderRadius: 8, borderWidth: 1, padding: 10, gap: 2 },
  sender: { color: "#1f2937", fontWeight: "700" },
  subject: { color: "#1f2937", fontSize: 16 },
  meta: { color: "#697386", fontSize: 12 },
  body: { color: "#1f2937", fontSize: 15, lineHeight: 22, marginTop: 4 },
  input: { borderColor: "#cbd5e1", borderRadius: 8, borderWidth: 1, minHeight: 44, paddingHorizontal: 10 },
  composeBody: { minHeight: 110, paddingTop: 10, textAlignVertical: "top" },
  primaryButton: { alignItems: "center", backgroundColor: "#176b5f", borderRadius: 8, minHeight: 44, justifyContent: "center" },
  primaryButtonText: { color: "#ffffff", fontWeight: "700" },
  secondaryButton: {
    alignItems: "center",
    borderColor: "#cbd5e1",
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 38,
    justifyContent: "center",
    paddingHorizontal: 12,
  },
  dangerButton: {
    alignItems: "center",
    backgroundColor: "#7f1d1d",
    borderRadius: 8,
    minHeight: 38,
    justifyContent: "center",
    paddingHorizontal: 12,
  },
  dangerButtonText: { color: "#ffffff", fontWeight: "700" },
  disabledButton: { opacity: 0.45 },
  statusBar: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 28 },
  statusText: { color: "#374151", flex: 1 },
});
