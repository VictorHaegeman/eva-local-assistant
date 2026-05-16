import { useEffect, useState } from "react";
import { ShieldCheck, Sparkles } from "lucide-react";

import { getDoctor, getHealth, getModes, sendChat } from "./api";
import { ChatInput } from "./components/ChatInput";
import { ChatWindow } from "./components/ChatWindow";
import { ControlPanel } from "./components/ControlPanel";
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
  const [mode, setMode] = useState("chat");
  const [activePanel, setActivePanel] = useState("chat");
  const [modes, setModes] = useState([]);
  const [doctor, setDoctor] = useState({
    status: "checking",
    summary: "Diagnostic en cours",
    checks: [],
  });
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

    getModes()
      .then((availableModes) => {
        if (!cancelled) {
          setModes(availableModes);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setModes([]);
        }
      });

    getDoctor()
      .then((diagnostic) => {
        if (!cancelled) {
          setDoctor(diagnostic);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDoctor({
            status: "error",
            summary: "Doctor indisponible",
            checks: [],
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

    setActivePanel("chat");

    const userMessage = createMessage("user", cleanText);
    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setLoading(true);
    setError("");

    try {
      const conversation = nextMessages
        .filter((message) => !message.localOnly)
        .map(({ role, content }) => ({ role, content }));

      const assistantMessage = await sendChat(conversation, mode);
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
    setActivePanel("chat");
  }

  function handleQuickPrompt(prompt) {
    setActivePanel("chat");
    handleSend(prompt);
  }

  const currentMode = modes.find((item) => item.name === mode);

  return (
    <main className="app-shell">
      <Sidebar
        status={backendStatus}
        doctor={doctor}
        modes={modes}
        activeMode={mode}
        activePanel={activePanel}
        onModeChange={setMode}
        onPanelChange={setActivePanel}
        onReset={handleReset}
      />

      <section className="chat-shell" aria-label="Conversation avec Eva">
        <header className="desktop-header">
          <div>
            <span className="eyebrow">Eva local core</span>
            <h2>{currentMode ? `Mode ${currentMode.label}` : "Assistant personnel"}</h2>
          </div>
          <div className="desktop-status">
            <ShieldCheck size={16} aria-hidden="true" />
            <span>{backendStatus.state === "ready" ? "Ollama connecte" : "Connexion Ollama"}</span>
            {backendStatus.model && <span className="model-pill">{backendStatus.model}</span>}
          </div>
        </header>

        <header className="mobile-header">
          <div>
            <div className="mobile-brand">
              <Sparkles size={18} aria-hidden="true" />
              Eva
            </div>
            <p>{currentMode ? `Mode ${currentMode.label}` : backendStatus.state === "ready" ? "Connectee en local" : "Connexion locale"}</p>
          </div>
          <span className={`status-dot ${backendStatus.state}`} />
        </header>

        {activePanel === "chat" ? (
          <ChatWindow
            messages={messages}
            loading={loading}
            error={error}
            status={backendStatus}
            onStarterSelect={handleSend}
          />
        ) : (
          <ControlPanel panel={activePanel} doctor={doctor} onPrompt={handleQuickPrompt} />
        )}

        <ChatInput onSend={handleSend} disabled={loading} />
      </section>
    </main>
  );
}
