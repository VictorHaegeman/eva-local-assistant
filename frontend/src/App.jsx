import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

import { getHealth, sendChat } from "./api";
import { ChatInput } from "./components/ChatInput";
import { ChatWindow } from "./components/ChatWindow";
import { Sidebar } from "./components/Sidebar";
import "./styles.css";


const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  content: "Bonjour Victor. Eva en ligne. Que veux-tu piloter ?",
  localOnly: true,
};

function createMessage(role, content) {
  return {
    id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`,
    role,
    content,
  };
}

export default function App() {
  const [messages, setMessages] = useState([welcomeMessage]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [backendStatus, setBackendStatus] = useState({
    state: "checking",
    model: "",
  });

  useEffect(() => {
    let cancelled = false;

    getHealth()
      .then((health) => {
        if (!cancelled) {
          setBackendStatus({
            state: "ready",
            model: health.model,
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBackendStatus({
            state: "offline",
            model: "",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSend(text) {
    const cleanText = text.trim();
    if (!cleanText || loading) return;

    const userMessage = createMessage("user", cleanText);
    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setLoading(true);
    setError("");

    try {
      const conversation = nextMessages
        .filter((message) => !message.localOnly)
        .map(({ role, content }) => ({ role, content }));

      const assistantMessage = await sendChat(conversation);
      setMessages((currentMessages) => [
        ...currentMessages,
        createMessage("assistant", assistantMessage.content),
      ]);
      setBackendStatus((current) => ({
        state: "ready",
        model: current.model,
      }));
    } catch (requestError) {
      setError(requestError.message);
      setBackendStatus((current) => ({
        state: "offline",
        model: current.model,
      }));
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setMessages([welcomeMessage]);
    setError("");
  }

  return (
    <main className="app-shell">
      <Sidebar status={backendStatus} onReset={handleReset} />

      <section className="chat-shell" aria-label="Conversation avec Eva">
        <header className="mobile-header">
          <div>
            <div className="mobile-brand">
              <Sparkles size={18} aria-hidden="true" />
              Eva
            </div>
            <p>{backendStatus.state === "ready" ? "Connectee en local" : "Connexion locale"}</p>
          </div>
          <span className={`status-dot ${backendStatus.state}`} />
        </header>

        <ChatWindow
          messages={messages}
          loading={loading}
          error={error}
          onStarterSelect={handleSend}
        />

        <ChatInput onSend={handleSend} disabled={loading} />
      </section>
    </main>
  );
}
