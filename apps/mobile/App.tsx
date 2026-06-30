import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  createMailboxSession,
  loadMailboxMessage,
  loadMailboxSnapshot,
  MailboxSession,
  MailMessage,
  MailMessageDetail,
  revokeMailboxSession,
  sendMailboxMessage,
} from "./src/api";
import { clearStoredMailboxSession, loadStoredMailboxSession, saveMailboxSession } from "./src/sessionStore";

const defaultApiBaseUrl = "https://freemail.kuzuryu.ai";

export default function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(defaultApiBaseUrl);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [session, setSession] = useState<MailboxSession | null>(null);
  const [folder, setFolder] = useState("INBOX");
  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [selectedMessage, setSelectedMessage] = useState<MailMessageDetail | null>(null);
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
        refreshMailbox(stored, folder);
      }
    });
  }, []);

  const selectedSubject = useMemo(() => selectedMessage?.subject || "Select a message", [selectedMessage]);

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
    setMessages([]);
    setSelectedMessage(null);
    await clearStoredMailboxSession();
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
      const snapshot = await loadMailboxSnapshot(activeSession, targetFolder);
      setFolder(targetFolder);
      setMessages(snapshot.messages || []);
      setSelectedMessage(null);
      setStatus(`Loaded ${snapshot.messages?.length || 0} messages from ${targetFolder}.`);
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
          <View style={styles.workspace}>
            <View style={styles.listPanel}>
              <View style={styles.rowHeader}>
                <Text style={styles.sectionTitle}>{folder}</Text>
                <Pressable style={styles.secondaryButton} onPress={() => refreshMailbox()}>
                  <Text>Refresh</Text>
                </Pressable>
              </View>
              <FlatList
                data={messages}
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
          </View>
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

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f5f7fb" },
  container: { flex: 1, padding: 16, gap: 12 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  eyebrow: { color: "#5c667a", fontSize: 12, textTransform: "uppercase" },
  title: { color: "#162032", fontSize: 28, fontWeight: "700" },
  panel: { backgroundColor: "#ffffff", borderRadius: 8, padding: 12, gap: 10 },
  workspace: { flex: 1, gap: 12 },
  listPanel: { backgroundColor: "#ffffff", borderRadius: 8, padding: 12, minHeight: 220 },
  readerPanel: { backgroundColor: "#ffffff", borderRadius: 8, padding: 12, minHeight: 140 },
  rowHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  sectionTitle: { color: "#1c2638", fontSize: 18, fontWeight: "700" },
  messageRow: { borderBottomColor: "#d8dee9", borderBottomWidth: 1, paddingVertical: 10, gap: 3 },
  sender: { color: "#1f2937", fontWeight: "700" },
  subject: { color: "#1f2937", fontSize: 16 },
  meta: { color: "#697386", fontSize: 12 },
  body: { color: "#1f2937", fontSize: 15, lineHeight: 22, marginTop: 10 },
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
  statusBar: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 28 },
  statusText: { color: "#374151", flex: 1 },
});
