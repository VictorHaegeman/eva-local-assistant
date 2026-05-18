import { useEffect, useState } from "react";
import { ShieldCheck, Sparkles } from "lucide-react";

import {
  getDailyLaunchBrief,
  getChatHistoryMessages,
  getDoctor,
  getHealth,
  getModes,
  openBrowserTabs,
  sendChat,
} from "./api";
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

function createDailyBriefMessage(payload) {
  const brief = payload.brief || {};
  const instagram = payload.instagram || {};
  const instagramLine = instagram.enabled
    ? `\n\nInstagram: ${instagram.summary || "check public effectue."}\n${instagram.limits || ""}`
    : "\n\nInstagram: pas encore configure en lecture publique.";
  const staleLine = payload.stale ? "Brief base sur le dernier brief disponible.\n\n" : "";

  return {
    id: `daily-${payload.date || Date.now()}`,
    role: "assistant",
    content: `${staleLine}${brief.content || "Je n'ai pas encore de brief disponible."}${instagramLine}`,
    briefItems: payload.visual_items || [],
    suggestedTabs: payload.suggested_tabs || [],
    instagram,
    localOnly: true,
  };
}

function createMessage(role, content) {
  return {
    id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`,
    role,
    content,
  };
}

export default function App() {
  const [messages, setMessages] = useState([welcomeMessage]);
  const [sessionId, setSessionId] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem("evaChatSessionId") || "";
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [voiceReplies, setVoiceReplies] = useState(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem("evaVoiceReplies") !== "false";
  });
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

    getDailyLaunchBrief()
      .then((payload) => {
        if (cancelled || !payload?.should_show || !payload.brief) {
          return;
        }

        setMessages((currentMessages) => [
          ...currentMessages,
          createDailyBriefMessage(payload),
        ]);
        speakEva(`Voici ton brief du jour. ${payload.brief.content || ""}`);

        if (payload.auto_open_tabs && Array.isArray(payload.suggested_tabs)) {
          const urls = payload.suggested_tabs
            .slice(0, 3)
            .map((tab) => tab?.url)
            .filter(Boolean);
          if (urls.length) {
            openBrowserTabs(urls).catch(() => {
              urls.forEach((url, index) => {
                window.setTimeout(() => {
                  window.open(url, "_blank", "noopener,noreferrer");
                }, 450 * (index + 1));
              });
            });
          }
        }
      })
      .catch(() => {
        // Le brief du jour ne doit pas bloquer le chat si une source RSS ne repond pas.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    window.localStorage.setItem("evaVoiceReplies", String(voiceReplies));
  }, [voiceReplies]);

  function speakEva(text) {
    if (!voiceReplies || typeof window === "undefined" || !window.speechSynthesis) {
      return;
    }

    const cleanText = text
      .replace(/\s+/g, " ")
      .replace(/https?:\/\/\S+/g, "")
      .trim()
      .slice(0, 900);

    if (!cleanText) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = "fr-FR";
    utterance.rate = 1.02;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  }

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

      const response = await sendChat(conversation, mode, sessionId);
      const assistantMessage = response.message;
      if (response.session_id) {
        setSessionId(response.session_id);
        window.localStorage.setItem("evaChatSessionId", response.session_id);
      }
      setMessages((currentMessages) => [
        ...currentMessages,
        createMessage("assistant", assistantMessage.content),
      ]);
      speakEva(assistantMessage.content);
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

  async function handleLoadChatSession(nextSessionId) {
    if (!nextSessionId) return;
    setLoading(true);
    setError("");

    try {
      const payload = await getChatHistoryMessages(nextSessionId);
      const loadedMessages = (payload.messages || [])
        .filter((message) => message.role === "user" || message.role === "assistant")
        .map((message) => ({
          id: `history-${message.id}`,
          role: message.role,
          content: message.content,
        }));

      setSessionId(nextSessionId);
      window.localStorage.setItem("evaChatSessionId", nextSessionId);
      setMessages(loadedMessages.length ? loadedMessages : [welcomeMessage]);
      setActivePanel("chat");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setMessages([welcomeMessage]);
    setSessionId("");
    window.localStorage.removeItem("evaChatSessionId");
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
          <ControlPanel
            panel={activePanel}
            doctor={doctor}
            onPrompt={handleQuickPrompt}
            onLoadChatSession={handleLoadChatSession}
          />
        )}

        <ChatInput
          onSend={handleSend}
          disabled={loading}
          voiceReplies={voiceReplies}
          onVoiceRepliesChange={setVoiceReplies}
        />
      </section>
    </main>
  );
}
