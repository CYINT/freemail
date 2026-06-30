import { StatusBar } from "expo-status-bar";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
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
  archiveMailboxMessage,
  bulkMailboxMessageAction,
  ComposeAttachment,
  createMailboxPushNotification,
  createMailboxFolder,
  createMailboxSession,
  deleteMailboxContact,
  deleteMailboxFolder,
  emptyMailboxFolder,
  loadMailboxAttachment,
  loadMailboxContacts,
  loadMailboxMessage,
  loadMailboxMessageSource,
  loadMailboxPreferences,
  loadMailboxPushDevices,
  loadMailboxPushNotifications,
  loadMailboxSnapshot,
  loadMailboxThread,
  loadSavedMailboxContacts,
  MailAttachment,
  MailboxPreferences,
  MailboxSession,
  MailContact,
  MailFolder,
  MailMessage,
  MailMessageDetail,
  MailboxPushDevice,
  MailboxPushNotification,
  moveMailboxMessage,
  renameMailboxFolder,
  registerMailboxPushDevice,
  revokeMailboxSession,
  revokeMailboxPushDevice,
  searchMailbox,
  saveMailboxDraft,
  saveMailboxContact,
  SavedMailContact,
  sendMailboxMessage,
  setMailboxMessageReadState,
  setMailboxMessageStarState,
  updateMailboxPreferences,
} from "./src/api";
import { clearCachedMailboxSnapshots, loadCachedMailboxSnapshot, saveCachedMailboxSnapshot } from "./src/offlineCache";
import { clearStoredMailboxSession, loadStoredMailboxSession, saveMailboxSession } from "./src/sessionStore";

const defaultApiBaseUrl = "https://freemail.kuzuryu.ai";
const mailboxPageSize = 25;
const maxComposeAttachments = 5;
const maxComposeAttachmentBytes = 1_048_576;
const allowedComposeAttachmentTypes = new Set(["text/plain", "text/csv", "application/pdf", "image/png", "image/jpeg"]);
const protectedFolders = new Set(["INBOX", "Archive", "Deleted Items", "Junk Mail", "Sent Items", "Drafts"]);
const emptyProtectedFolders = new Set(["INBOX", "Archive", "Sent Items", "Drafts"]);

type SelectedComposeAttachment = ComposeAttachment & {
  id: string;
  size: number;
};

type MailboxPagination = {
  mode: "folder" | "search";
  query: string;
  nextOffset: number | null;
  hasMore: boolean;
};

export default function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(defaultApiBaseUrl);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [session, setSession] = useState<MailboxSession | null>(null);
  const [folder, setFolder] = useState("INBOX");
  const [folders, setFolders] = useState<MailFolder[]>([]);
  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [mailboxPagination, setMailboxPagination] = useState<MailboxPagination>({
    mode: "folder",
    query: "",
    nextOffset: null,
    hasMore: false,
  });
  const [selectedMessageIds, setSelectedMessageIds] = useState<string[]>([]);
  const [contacts, setContacts] = useState<MailContact[]>([]);
  const [savedContacts, setSavedContacts] = useState<SavedMailContact[]>([]);
  const [pushDevices, setPushDevices] = useState<MailboxPushDevice[]>([]);
  const [pushNotifications, setPushNotifications] = useState<MailboxPushNotification[]>([]);
  const [selectedMessage, setSelectedMessage] = useState<MailMessageDetail | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [newFolderName, setNewFolderName] = useState("");
  const [renameFolderName, setRenameFolderName] = useState("");
  const [savedContactName, setSavedContactName] = useState("");
  const [savedContactEmail, setSavedContactEmail] = useState("");
  const [pushDeviceId, setPushDeviceId] = useState("");
  const [pushToken, setPushToken] = useState("");
  const [mailboxPreferences, setMailboxPreferences] = useState<MailboxPreferences | null>(null);
  const [preferenceDisplayName, setPreferenceDisplayName] = useState("");
  const [preferenceSignature, setPreferenceSignature] = useState("");
  const [composeTo, setComposeTo] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [composeAttachments, setComposeAttachments] = useState<SelectedComposeAttachment[]>([]);
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
  const canEmptyFolder = !emptyProtectedFolders.has(folder);

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
    setMailboxPagination({ mode: "folder", query: "", nextOffset: null, hasMore: false });
    setContacts([]);
    setSavedContacts([]);
    setPushDevices([]);
    setPushNotifications([]);
    setMailboxPreferences(null);
    setPreferenceDisplayName("");
    setPreferenceSignature("");
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

  async function refreshMailbox(activeSession = session, targetFolder = folder, offset = 0, append = false) {
    if (!activeSession) {
      return;
    }
    setLoading(true);
    setStatus(append ? `Loading more ${targetFolder}...` : `Loading ${targetFolder}...`);
    try {
      const cached = !append ? await loadCachedMailboxSnapshot(activeSession, targetFolder) : null;
      if (cached) {
        setFolder(cached.folder);
        setFolders(cached.folders);
        setMessages(cached.messages);
        setContacts(cached.contacts);
        setStatus(`Showing cached ${cached.folder} from ${formatCachedAt(cached.cachedAt)}.`);
      }
      const [snapshot, contactList, preferences] = await Promise.all([
        loadMailboxSnapshot(activeSession, targetFolder, offset, mailboxPageSize),
        loadMailboxContacts(activeSession, targetFolder),
        loadMailboxPreferences(activeSession),
      ]);
      const savedContactList = await loadSavedMailboxContacts(activeSession);
      const devices = await loadMailboxPushDevices(activeSession);
      const notifications = await loadMailboxPushNotifications(activeSession);
      setFolder(targetFolder);
      setFolders(snapshot.folders || []);
      setMessages((current) => (append ? [...current, ...(snapshot.messages || [])] : snapshot.messages || []));
      if (!append) {
        setSelectedMessageIds([]);
        setSelectedMessage(null);
      }
      setMailboxPagination({
        mode: "folder",
        query: "",
        nextOffset: snapshot.nextOffset ?? null,
        hasMore: Boolean(snapshot.hasMore),
      });
      setContacts(contactList.contacts || []);
      setSavedContacts(savedContactList.contacts || []);
      setPushDevices(devices || []);
      setPushNotifications(notifications || []);
      setMailboxPreferences(preferences);
      setPreferenceDisplayName(preferences.displayName || "");
      setPreferenceSignature(preferences.signature || "");
      if (!append) {
        await saveCachedMailboxSnapshot(activeSession, targetFolder, snapshot, contactList.contacts || []);
      }
      setStatus(
        append
          ? `Loaded ${snapshot.messages?.length || 0} more messages from ${targetFolder}.`
          : `Loaded ${snapshot.messages?.length || 0} messages from ${targetFolder}.`,
      );
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function savePreferences() {
    if (!session) {
      return;
    }
    setLoading(true);
    setStatus("Saving preferences...");
    try {
      const saved = await updateMailboxPreferences(session, {
        displayName: preferenceDisplayName.trim(),
        signature: preferenceSignature.trim(),
      });
      setMailboxPreferences(saved);
      setPreferenceDisplayName(saved.displayName || "");
      setPreferenceSignature(saved.signature || "");
      setStatus("Preferences saved.");
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function saveContact() {
    if (!session || !savedContactEmail.trim()) {
      setStatus("Enter a contact email before saving.");
      return;
    }
    setLoading(true);
    setStatus("Saving contact...");
    try {
      await saveMailboxContact(session, savedContactEmail.trim(), savedContactName.trim());
      const saved = await loadSavedMailboxContacts(session);
      setSavedContacts(saved.contacts || []);
      setSavedContactName("");
      setSavedContactEmail("");
      setStatus("Contact saved.");
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function deleteContact(contactId: number) {
    if (!session) {
      return;
    }
    setLoading(true);
    setStatus("Deleting contact...");
    try {
      await deleteMailboxContact(session, contactId);
      const saved = await loadSavedMailboxContacts(session);
      setSavedContacts(saved.contacts || []);
      setStatus("Contact deleted.");
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function registerPushDevice() {
    if (!session || !pushDeviceId.trim() || !pushToken.trim()) {
      return;
    }
    setLoading(true);
    setStatus("Registering push device...");
    try {
      const registered = await registerMailboxPushDevice(session, pushDeviceId.trim(), pushToken.trim());
      setPushToken("");
      setPushDevices((current) => [registered, ...current.filter((device) => device.deviceId !== registered.deviceId)]);
      setStatus(`Push device ${registered.deviceId} registered.`);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function revokePushDevice(deviceId: string) {
    if (!session) {
      return;
    }
    setLoading(true);
    setStatus(`Revoking push device ${deviceId}...`);
    try {
      await revokeMailboxPushDevice(session, deviceId);
      setPushDevices((current) =>
        current.map((device) => (device.deviceId === deviceId ? { ...device, enabled: false } : device)),
      );
      setStatus(`Push device ${deviceId} revoked.`);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function sendTestPushNotification() {
    if (!session) {
      return;
    }
    setLoading(true);
    setStatus("Sending push test...");
    try {
      const notifications = await createMailboxPushNotification(session, "FreeMail", "Push delivery test");
      setPushNotifications(notifications);
      setStatus(`Push test created for ${notifications.length} devices.`);
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
      setSelectedMessageIds([]);
      setSelectedMessage(null);
      setMailboxPagination({
        mode: "search",
        query,
        nextOffset: result.nextOffset ?? null,
        hasMore: Boolean(result.hasMore),
      });
      setStatus(`Found ${result.messages?.length || 0} messages in ${folder}.`);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function loadMoreMessages() {
    if (!session || !mailboxPagination.hasMore || mailboxPagination.nextOffset === null) {
      return;
    }
    setLoading(true);
    try {
      if (mailboxPagination.mode === "search") {
        const result = await searchMailbox(
          session,
          folder,
          mailboxPagination.query,
          mailboxPagination.nextOffset,
          mailboxPageSize,
        );
        setMessages((current) => [...current, ...(result.messages || [])]);
        setMailboxPagination({
          mode: "search",
          query: mailboxPagination.query,
          nextOffset: result.nextOffset ?? null,
          hasMore: Boolean(result.hasMore),
        });
        setStatus(`Loaded ${result.messages?.length || 0} more matches.`);
        return;
      }
      await refreshMailbox(session, folder, mailboxPagination.nextOffset, true);
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

  async function loadSelectedThread() {
    if (!session || !selectedMessage?.threadId) {
      setStatus("Open a message before loading the conversation.");
      return;
    }
    setLoading(true);
    setStatus("Loading conversation...");
    try {
      const thread = await loadMailboxThread(session, selectedMessage.folder, selectedMessage.threadId);
      setMessages(thread.messages || []);
      setSelectedMessage(null);
      setSelectedMessageIds([]);
      setMailboxPagination({ mode: "folder", query: "", nextOffset: null, hasMore: false });
      setStatus(`Loaded ${thread.messages?.length || 0} conversation messages.`);
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
      const sent = await sendMailboxMessage(session, composePayload());
      setComposeTo("");
      setComposeSubject("");
      setComposeBody("");
      setComposeAttachments([]);
      setStatus(
        sent.sentFolderSaved
          ? `Message sent and saved to ${sent.sentFolder || "Sent Items"}.`
          : "Message sent, but Sent Items was not updated.",
      );
      await refreshMailbox(session, folder);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function saveDraft() {
    if (!session) {
      return;
    }
    setLoading(true);
    setStatus("Saving draft...");
    try {
      const draft = await saveMailboxDraft(session, composePayload());
      setStatus(`Draft saved to ${draft.draftFolder || "Drafts"}.`);
      await refreshMailbox(session, folder);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  function composePayload() {
    return {
      recipients: composeTo
        .split(",")
        .map((recipient) => recipient.trim())
        .filter(Boolean),
      subject: composeSubject.trim(),
      body: withSignature(composeBody),
      attachments: composeAttachments.map(({ filename, contentType, contentBase64 }) => ({
        filename,
        contentType,
        contentBase64,
      })),
    };
  }

  function withSignature(body: string) {
    const signature = (mailboxPreferences?.signature || preferenceSignature).trim();
    if (!signature || body.includes(signature)) {
      return body;
    }
    return `${body}${body.trim() ? "\n\n-- \n" : "-- \n"}${signature}`;
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

  async function emptyCurrentFolder() {
    if (!session || !canEmptyFolder) {
      return;
    }
    setLoading(true);
    setStatus(`Emptying ${folder}...`);
    try {
      const result = await emptyMailboxFolder(session, folder);
      await refreshMailbox(session, folder);
      setStatus(`Emptied ${folder}; deleted ${result.deletedCount || 0} messages.`);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  function confirmEmptyCurrentFolder() {
    if (!canEmptyFolder) {
      return;
    }
    Alert.alert("Empty folder", `Permanently delete every message in ${folder}?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Empty", style: "destructive", onPress: emptyCurrentFolder },
    ]);
  }

  function replyToSelectedMessage() {
    if (!selectedMessage) {
      return;
    }
    setComposeTo(selectedMessage.sender);
    setComposeSubject(prefixedSubject("Re:", selectedMessage.subject));
    setComposeBody(withSignature(`\n\nOn ${selectedMessage.date}, ${selectedMessage.sender} wrote:\n${quoteBody(selectedMessage.body)}`));
  }

  function forwardSelectedMessage() {
    if (!selectedMessage) {
      return;
    }
    setComposeTo("");
    setComposeSubject(prefixedSubject("Fwd:", selectedMessage.subject));
    setComposeBody(
      withSignature(
        `\n\nForwarded message\nFrom: ${selectedMessage.sender}\nTo: ${selectedMessage.recipients}\n\n${selectedMessage.body}`,
      ),
    );
  }

  function editSelectedDraft() {
    if (!selectedMessage || !isDraftMessage(selectedMessage)) {
      return;
    }
    setComposeTo(selectedMessage.recipients);
    setComposeSubject(selectedMessage.subject === "(no subject)" ? "" : selectedMessage.subject);
    setComposeBody(selectedMessage.body || "");
    setComposeAttachments([]);
    setStatus(
      selectedMessage.attachments?.length
        ? "Draft loaded into compose. Reattach files before saving or sending."
        : "Draft loaded into compose.",
    );
  }

  async function pickComposeAttachments() {
    const remainingSlots = maxComposeAttachments - composeAttachments.length;
    if (remainingSlots <= 0) {
      setStatus(`Attach up to ${maxComposeAttachments} files.`);
      return;
    }
    setLoading(true);
    setStatus("Selecting attachments...");
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: [...allowedComposeAttachmentTypes],
        copyToCacheDirectory: true,
        multiple: true,
        base64: false,
      });
      if (result.canceled) {
        setStatus("Attachment selection cancelled.");
        return;
      }
      const selected = await Promise.all(result.assets.slice(0, remainingSlots).map(composeAttachmentFromAsset));
      setComposeAttachments((current) => [...current, ...selected]);
      setStatus(`Added ${selected.length} attachments.`);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  function removeComposeAttachment(id: string) {
    setComposeAttachments((current) => current.filter((attachment) => attachment.id !== id));
  }

  async function downloadAndShareAttachment(attachment: MailAttachment) {
    if (!session || !selectedMessage) {
      return;
    }
    setLoading(true);
    setStatus(`Downloading attachment ${attachment.filename}...`);
    try {
      const blob = await loadMailboxAttachment(session, selectedMessage.folder, selectedMessage.messageId, attachment.attachmentId);
      const localUri = await writeAttachmentToCache(attachment, blob);
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(localUri, {
          dialogTitle: `Save ${attachment.filename}`,
          mimeType: attachment.contentType,
        });
        setStatus(`Attachment ready to save: ${attachment.filename}.`);
      } else {
        setStatus(`Attachment downloaded to app cache: ${attachment.filename} (${formatBytes(blob.size)}).`);
      }
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function downloadAndShareMessageSource() {
    if (!session || !selectedMessage) {
      return;
    }
    setLoading(true);
    setStatus("Exporting message source...");
    try {
      const blob = await loadMailboxMessageSource(session, selectedMessage.folder, selectedMessage.messageId);
      const localUri = await writeMessageSourceToCache(selectedMessage, blob);
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(localUri, {
          dialogTitle: "Save message.eml",
          mimeType: "message/rfc822",
        });
        setStatus("Message EML ready to save.");
      } else {
        setStatus(`Message EML exported to app cache (${formatBytes(blob.size)}).`);
      }
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function archiveSelectedMessage() {
    if (!session || !selectedMessage) {
      return;
    }
    setLoading(true);
    setStatus("Archiving message...");
    try {
      await archiveMailboxMessage(session, selectedMessage.folder, selectedMessage.messageId);
      setSelectedMessage(null);
      await refreshMailbox(session, folder);
      setStatus("Message archived.");
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function moveSelectedMessage(targetFolder: string, successMessage: string) {
    if (!session || !selectedMessage) {
      return;
    }
    setLoading(true);
    setStatus(`Moving message to ${targetFolder}...`);
    try {
      await moveMailboxMessage(session, selectedMessage.folder, selectedMessage.messageId, targetFolder);
      setSelectedMessage(null);
      await refreshMailbox(session, folder);
      setStatus(successMessage);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function bulkAction(
    action: "read" | "unread" | "star" | "unstar" | "archive" | "spam" | "delete",
    successMessage: string,
  ) {
    if (!session || !selectedMessageIds.length) {
      setStatus("Select messages before using bulk actions.");
      return;
    }
    setLoading(true);
    setStatus(`Applying ${action} to ${selectedMessageIds.length} messages...`);
    try {
      const result = await bulkMailboxMessageAction(session, folder, selectedMessageIds, action);
      setSelectedMessageIds([]);
      setSelectedMessage(null);
      await refreshMailbox(session, folder);
      setStatus(`${successMessage} ${result.succeeded}/${result.messageIds.length} updated.`);
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function setSelectedMessageReadState(read: boolean) {
    if (!session || !selectedMessage) {
      return;
    }
    setLoading(true);
    setStatus(read ? "Marking message read..." : "Marking message unread...");
    try {
      await setMailboxMessageReadState(session, selectedMessage.folder, selectedMessage.messageId, read);
      setSelectedMessage({ ...selectedMessage, unread: !read });
      await refreshMailbox(session, folder);
      setStatus(read ? "Message marked read." : "Message marked unread.");
    } catch (error) {
      setStatus(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function setSelectedMessageStarState(starred: boolean) {
    if (!session || !selectedMessage) {
      return;
    }
    setLoading(true);
    setStatus(starred ? "Starring message..." : "Unstarring message...");
    try {
      await setMailboxMessageStarState(session, selectedMessage.folder, selectedMessage.messageId, starred);
      setSelectedMessage({ ...selectedMessage, starred });
      await refreshMailbox(session, folder);
      setStatus(starred ? "Message starred." : "Message unstarred.");
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

  function toggleMessageSelection(messageId: string) {
    setSelectedMessageIds((current) =>
      current.includes(messageId) ? current.filter((value) => value !== messageId) : [...current, messageId],
    );
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
                <Pressable style={[styles.secondaryButton, !canEmptyFolder ? styles.disabledButton : null]} onPress={confirmEmptyCurrentFolder}>
                  <Text>Empty</Text>
                </Pressable>
                <Pressable style={[styles.dangerButton, !canMutateFolder ? styles.disabledButton : null]} onPress={deleteCurrentFolder}>
                  <Text style={styles.dangerButtonText}>Delete</Text>
                </Pressable>
              </View>
            </View>

            <View style={styles.listPanel}>
              <View style={styles.rowHeader}>
                <Text style={styles.sectionTitle}>Messages</Text>
                <Text style={styles.meta}>{selectedMessageIds.length} selected</Text>
              </View>
              <View style={styles.inlineControls}>
                <Pressable style={styles.secondaryButton} onPress={() => bulkAction("read", "Messages marked read.")}>
                  <Text>Read</Text>
                </Pressable>
                <Pressable style={styles.secondaryButton} onPress={() => bulkAction("unread", "Messages marked unread.")}>
                  <Text>Unread</Text>
                </Pressable>
                <Pressable style={styles.secondaryButton} onPress={() => bulkAction("star", "Messages starred.")}>
                  <Text>Star</Text>
                </Pressable>
                <Pressable style={styles.secondaryButton} onPress={() => bulkAction("unstar", "Messages unstarred.")}>
                  <Text>Unstar</Text>
                </Pressable>
                <Pressable style={styles.secondaryButton} onPress={() => bulkAction("archive", "Messages archived.")}>
                  <Text>Archive</Text>
                </Pressable>
                <Pressable style={styles.secondaryButton} onPress={() => bulkAction("spam", "Messages moved to spam.")}>
                  <Text>Spam</Text>
                </Pressable>
                <Pressable style={styles.dangerButton} onPress={() => bulkAction("delete", "Messages deleted.")}>
                  <Text style={styles.dangerButtonText}>Delete</Text>
                </Pressable>
              </View>
              <FlatList
                data={messages}
                scrollEnabled={false}
                keyExtractor={(item) => `${item.folder}:${item.messageId}`}
                renderItem={({ item }) => (
                  <Pressable style={styles.messageRow} onPress={() => openMessage(item)}>
                    <Pressable
                      style={[styles.selectionPill, selectedMessageIds.includes(item.messageId) ? styles.selectedPill : null]}
                      onPress={() => toggleMessageSelection(item.messageId)}
                    >
                      <Text style={selectedMessageIds.includes(item.messageId) ? styles.selectedPillText : styles.selectionPillText}>
                        {selectedMessageIds.includes(item.messageId) ? "Selected" : "Select"}
                      </Text>
                    </Pressable>
                    <Text style={styles.sender}>{item.sender || "Unknown sender"}</Text>
                    <Text style={styles.subject}>{item.starred ? `* ${item.subject || "(no subject)"}` : item.subject || "(no subject)"}</Text>
                    {threadHint(item) ? <Text style={styles.threadHint}>{threadHint(item)}</Text> : null}
                    <Text style={styles.meta}>{item.recipients}</Text>
                  </Pressable>
                )}
              />
              {mailboxPagination.hasMore ? (
                <Pressable style={styles.secondaryButton} onPress={loadMoreMessages}>
                  <Text>{mailboxPagination.mode === "search" ? "Load more matches" : "Load more"}</Text>
                </Pressable>
              ) : null}
            </View>

            <View style={styles.readerPanel}>
              <Text style={styles.sectionTitle}>{selectedSubject}</Text>
              <Text style={styles.meta}>{selectedMessage ? readerMetadata(selectedMessage) : "Open a message to read it."}</Text>
              <Text style={styles.body}>{selectedMessage?.body || ""}</Text>
              {selectedMessage ? (
                <View style={styles.inlineControls}>
                  <Pressable style={styles.secondaryButton} onPress={replyToSelectedMessage}>
                    <Text>Reply</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={forwardSelectedMessage}>
                    <Text>Forward</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={loadSelectedThread}>
                    <Text>Conversation</Text>
                  </Pressable>
                  {isDraftMessage(selectedMessage) ? (
                    <Pressable style={styles.secondaryButton} onPress={editSelectedDraft}>
                      <Text>Edit draft</Text>
                    </Pressable>
                  ) : null}
                  <Pressable style={styles.secondaryButton} onPress={downloadAndShareMessageSource}>
                    <Text>Export EML</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => setSelectedMessageReadState(true)}>
                    <Text>Mark read</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => setSelectedMessageReadState(false)}>
                    <Text>Mark unread</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => setSelectedMessageStarState(true)}>
                    <Text>Star</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => setSelectedMessageStarState(false)}>
                    <Text>Unstar</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={archiveSelectedMessage}>
                    <Text>Archive</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => moveSelectedMessage("Junk Mail", "Message moved to spam.")}>
                    <Text>Spam</Text>
                  </Pressable>
                  <Pressable style={styles.dangerButton} onPress={() => moveSelectedMessage("Deleted Items", "Message deleted.")}>
                    <Text style={styles.dangerButtonText}>Delete</Text>
                  </Pressable>
                </View>
              ) : null}
              {selectedMessage?.attachments?.map((attachment) => (
                <View key={attachment.attachmentId} style={styles.attachmentRow}>
                  <View style={styles.attachmentDetails}>
                    <Text style={styles.subject}>{attachment.filename}</Text>
                    <Text style={styles.meta}>
                      {attachment.contentType} - {formatBytes(attachment.size)}
                    </Text>
                  </View>
                  <Pressable style={styles.secondaryButton} onPress={() => downloadAndShareAttachment(attachment)}>
                    <Text>Download</Text>
                  </Pressable>
                </View>
              ))}
            </View>

            <View style={styles.panel}>
              <Text style={styles.sectionTitle}>Contacts</Text>
              <View style={styles.inlineControls}>
                <TextInput
                  value={savedContactName}
                  onChangeText={setSavedContactName}
                  style={[styles.input, styles.flexInput]}
                  placeholder="Name"
                />
                <TextInput
                  value={savedContactEmail}
                  onChangeText={setSavedContactEmail}
                  style={[styles.input, styles.flexInput]}
                  autoCapitalize="none"
                  keyboardType="email-address"
                  placeholder="person@example.com"
                />
              </View>
              <Pressable style={styles.secondaryButton} onPress={saveContact}>
                <Text>Save contact</Text>
              </Pressable>
              {savedContacts.slice(0, 8).map((contact) => (
                <View key={contact.id} style={styles.contactRow}>
                  <Pressable onPress={() => addContactToDraft({ name: contact.displayName, email: contact.contactEmail, messageCount: 1 })}>
                    <Text style={styles.sender}>{contact.displayName || contact.contactEmail}</Text>
                    <Text style={styles.meta}>{contact.contactEmail} - saved</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => deleteContact(contact.id)}>
                    <Text>Delete</Text>
                  </Pressable>
                </View>
              ))}
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
              <Text style={styles.sectionTitle}>Push devices</Text>
              <View style={styles.inlineControls}>
                <TextInput
                  value={pushDeviceId}
                  onChangeText={setPushDeviceId}
                  style={[styles.input, styles.flexInput]}
                  autoCapitalize="none"
                  placeholder="Device ID"
                />
                <TextInput
                  value={pushToken}
                  onChangeText={setPushToken}
                  style={[styles.input, styles.flexInput]}
                  autoCapitalize="none"
                  placeholder="Provider token"
                  secureTextEntry
                />
              </View>
              <Pressable style={styles.secondaryButton} onPress={registerPushDevice}>
                <Text>Register push device</Text>
              </Pressable>
              <Pressable style={styles.secondaryButton} onPress={sendTestPushNotification}>
                <Text>Send push test</Text>
              </Pressable>
              {pushDevices.map((device) => (
                <View key={device.deviceId} style={styles.pushDeviceRow}>
                  <View>
                    <Text style={styles.sender}>{device.deviceId}</Text>
                    <Text style={styles.meta}>
                      {device.platform} - {device.provider} - {device.enabled ? "enabled" : "revoked"}
                    </Text>
                  </View>
                  {device.enabled ? (
                    <Pressable style={styles.secondaryButton} onPress={() => revokePushDevice(device.deviceId)}>
                      <Text>Revoke</Text>
                    </Pressable>
                  ) : null}
                </View>
              ))}
              {pushNotifications.map((notification) => (
                <View key={notification.id} style={styles.pushDeviceRow}>
                  <View>
                    <Text style={styles.sender}>{notification.title}</Text>
                    <Text style={styles.meta}>
                      {notification.deviceId} - {notification.provider} - {notification.status}
                    </Text>
                  </View>
                </View>
              ))}
            </View>

            <View style={styles.panel}>
              <Text style={styles.sectionTitle}>Preferences</Text>
              <TextInput
                value={preferenceDisplayName}
                onChangeText={setPreferenceDisplayName}
                style={styles.input}
                placeholder="Display name"
              />
              <TextInput
                value={preferenceSignature}
                onChangeText={setPreferenceSignature}
                style={[styles.input, styles.signatureInput]}
                multiline
                placeholder="Signature"
              />
              <Pressable style={styles.secondaryButton} onPress={savePreferences}>
                <Text>Save preferences</Text>
              </Pressable>
            </View>

            <View style={styles.panel}>
              <Text style={styles.sectionTitle}>Compose</Text>
              <TextInput value={composeTo} onChangeText={setComposeTo} style={styles.input} autoCapitalize="none" placeholder="To" />
              <TextInput value={composeSubject} onChangeText={setComposeSubject} style={styles.input} placeholder="Subject" />
              <TextInput value={composeBody} onChangeText={setComposeBody} style={[styles.input, styles.composeBody]} multiline placeholder="Message" />
              <Pressable style={styles.secondaryButton} onPress={pickComposeAttachments}>
                <Text>Add attachments</Text>
              </Pressable>
              {composeAttachments.map((attachment) => (
                <View key={attachment.id} style={styles.composeAttachmentRow}>
                  <View>
                    <Text style={styles.sender}>{attachment.filename}</Text>
                    <Text style={styles.meta}>
                      {attachment.contentType} - {formatBytes(attachment.size)}
                    </Text>
                  </View>
                  <Pressable style={styles.secondaryButton} onPress={() => removeComposeAttachment(attachment.id)}>
                    <Text>Remove</Text>
                  </Pressable>
                </View>
              ))}
              <Pressable style={styles.secondaryButton} onPress={saveDraft}>
                <Text>Save draft</Text>
              </Pressable>
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

function isDraftMessage(message: MailMessage | MailMessageDetail | null): boolean {
  return message?.folder === "Drafts";
}

function quoteBody(body: string): string {
  return body
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n");
}

async function composeAttachmentFromAsset(asset: DocumentPicker.DocumentPickerAsset): Promise<SelectedComposeAttachment> {
  const size = asset.size || 0;
  const contentType = asset.mimeType || "application/octet-stream";
  if (!allowedComposeAttachmentTypes.has(contentType)) {
    throw new Error(`Unsupported attachment type: ${contentType}`);
  }
  if (size > maxComposeAttachmentBytes) {
    throw new Error(`Attachment exceeds ${formatBytes(maxComposeAttachmentBytes)}: ${asset.name}`);
  }
  const contentBase64 =
    asset.base64 ||
    (await FileSystem.readAsStringAsync(asset.uri, {
      encoding: FileSystem.EncodingType.Base64,
    }));
  return {
    id: `${asset.name}:${size}:${Date.now()}:${Math.random().toString(36).slice(2)}`,
    filename: asset.name,
    contentType,
    contentBase64,
    size,
  };
}

async function writeAttachmentToCache(attachment: MailAttachment, blob: Blob): Promise<string> {
  if (!FileSystem.cacheDirectory) {
    throw new Error("Attachment cache is unavailable on this device.");
  }
  const attachmentId = safeCacheFilename(attachment.attachmentId);
  const filename = safeCacheFilename(attachment.filename || attachment.attachmentId);
  const localUri = `${FileSystem.cacheDirectory}freemail-${attachmentId}-${filename}`;
  await FileSystem.writeAsStringAsync(localUri, await blobToBase64(blob), {
    encoding: FileSystem.EncodingType.Base64,
  });
  return localUri;
}

async function writeMessageSourceToCache(message: MailMessageDetail, blob: Blob): Promise<string> {
  if (!FileSystem.cacheDirectory) {
    throw new Error("Message cache is unavailable on this device.");
  }
  const folder = safeCacheFilename(message.folder);
  const messageId = safeCacheFilename(message.messageId);
  const localUri = `${FileSystem.cacheDirectory}freemail-${folder}-${messageId}.eml`;
  await FileSystem.writeAsStringAsync(localUri, await blobToBase64(blob), {
    encoding: FileSystem.EncodingType.Base64,
  });
  return localUri;
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Attachment download could not be prepared."));
    reader.onloadend = () => {
      const dataUrl = String(reader.result || "");
      resolve(dataUrl.includes(",") ? dataUrl.split(",", 2)[1] : dataUrl);
    };
    reader.readAsDataURL(blob);
  });
}

function safeCacheFilename(filename: string): string {
  return filename.replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 96) || "attachment";
}

function formatCachedAt(cachedAt: string): string {
  if (!cachedAt) {
    return "offline cache";
  }
  return new Date(cachedAt).toLocaleString();
}

function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${Math.round(size / 102.4) / 10} KB`;
  }
  return `${Math.round(size / 104_857.6) / 10} MB`;
}

function threadHint(message: MailMessage): string {
  const subject = message.subject || "(no subject)";
  const threadSubject = message.threadSubject || subject;
  if (!message.inReplyTo && threadSubject === subject) {
    return "";
  }
  return `Thread: ${threadSubject}`;
}

function readerMetadata(message: MailMessage): string {
  const base = `From ${message.sender || "Unknown sender"}`;
  const threadSubject = message.threadSubject || message.subject || "(no subject)";
  return message.threadId ? `${base} | Thread ${threadSubject}` : base;
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
  inlineControls: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 8 },
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
  selectionPill: {
    alignItems: "center",
    alignSelf: "flex-start",
    borderColor: "#cbd5e1",
    borderRadius: 6,
    borderWidth: 1,
    minHeight: 30,
    justifyContent: "center",
    paddingHorizontal: 8,
  },
  selectedPill: { backgroundColor: "#176b5f", borderColor: "#176b5f" },
  selectionPillText: { color: "#1f2937", fontSize: 12, fontWeight: "700" },
  selectedPillText: { color: "#ffffff", fontSize: 12, fontWeight: "700" },
  contactRow: { borderBottomColor: "#eef2f7", borderBottomWidth: 1, paddingVertical: 8, gap: 2 },
  attachmentRow: {
    alignItems: "center",
    borderColor: "#cbd5e1",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
    padding: 10,
  },
  attachmentDetails: { flex: 1 },
  composeAttachmentRow: {
    alignItems: "center",
    borderColor: "#cbd5e1",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    padding: 10,
  },
  pushDeviceRow: {
    alignItems: "center",
    borderBottomColor: "#eef2f7",
    borderBottomWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 8,
  },
  sender: { color: "#1f2937", fontWeight: "700" },
  subject: { color: "#1f2937", fontSize: 16 },
  threadHint: { color: "#697386", fontSize: 12 },
  meta: { color: "#697386", fontSize: 12 },
  body: { color: "#1f2937", fontSize: 15, lineHeight: 22, marginTop: 4 },
  input: { borderColor: "#cbd5e1", borderRadius: 8, borderWidth: 1, minHeight: 44, paddingHorizontal: 10 },
  signatureInput: { minHeight: 92, paddingTop: 10, textAlignVertical: "top" },
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
