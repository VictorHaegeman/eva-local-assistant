import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, BrainCircuit, FileText, Radar, ShieldCheck, Sparkles } from "lucide-react";

import { EvaOrb } from "./EvaOrb";
import { MessageBubble } from "./MessageBubble";


const starters = [
  {
    label: "Brief DreamLense",
    prompt: "Prepare mon brief DreamLense.",
    icon: FileText,
  },
  {
    label: "Lire README",
    prompt: "Resume le fichier README.md.",
    icon: BrainCircuit,
  },
  {
    label: "Prompt Cursor",
    prompt: "Cree un prompt Cursor pour ameliorer Eva.",
    icon: Sparkles,
  },
];

const deckSignals = [
  {
    label: "Memoire",
    value: "Obsidian + local",
  },
  {
    label: "Actions",
    value: "PC local",
  },
  {
    label: "Mode",
    value: "Autonomie guidee",
  },
];

function normalizePrompt(text = "") {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}


function buildThinkingPlan(prompt = "") {
  const normalized = normalizePrompt(prompt);
  const wantsMap = /\b(carte|cartz|map|maps|plan|londres|london|londers|3d)\b/.test(normalized);
  const wantsMail = /\b(mail|gmail|inbox|message|repond|brouillon)\b/.test(normalized);
  const wantsProject = /\b(projet|cursor|codex|repo|github|code|coder)\b/.test(normalized);
  const wantsScreen = /\b(ecran|fenetre|clique|pixel|terminal|erreur)\b/.test(normalized);

  if (wantsMap) {
    return {
      intent: "Carte / navigation",
      routes: [
        { label: "Carte integree", score: 92 },
        { label: "Google Maps", score: 84 },
        { label: "Vue 3D", score: normalized.includes("3d") ? 91 : 58 },
      ],
      stages: [
        { label: "Comprendre", detail: "Identifier le lieu demande" },
        { label: "Corriger", detail: "Traiter les fautes type londers/londres" },
        { label: "Router", detail: "Choisir carte integree + liens externes" },
        { label: "Executer", detail: "Preparer la preview interactive" },
        { label: "Verifier", detail: "Confirmer coordonnees et actions utiles" },
      ],
    };
  }

  if (wantsMail) {
    return {
      intent: "Gmail / inbox",
      routes: [
        { label: "Lire mails reels", score: 88 },
        { label: "Verifier thread", score: 76 },
        { label: "Brouillon Gmail", score: normalized.includes("repond") ? 90 : 52 },
      ],
      stages: [
        { label: "Comprendre", detail: "Chercher le mail ou le sujet vise" },
        { label: "Contexte", detail: "Charger Gmail et l'historique utile" },
        { label: "Router", detail: "Lire, ouvrir ou rediger selon la demande" },
        { label: "Executer", detail: "Appeler les outils Gmail locaux" },
        { label: "Verifier", detail: "Ne pas inventer, ne pas envoyer seul" },
      ],
    };
  }

  if (wantsProject) {
    return {
      intent: "Projet / code",
      routes: [
        { label: "Resolver projet", score: 84 },
        { label: "Cursor prompt", score: 78 },
        { label: "Agent local", score: 64 },
      ],
      stages: [
        { label: "Comprendre", detail: "Trouver le vrai objectif" },
        { label: "Contexte", detail: "Comparer aux projets connus" },
        { label: "Planifier", detail: "Choisir workspace, repo ou prompt" },
        { label: "Executer", detail: "Preparer l'action locale" },
        { label: "Verifier", detail: "Auditer le resultat attendu" },
      ],
    };
  }

  if (wantsScreen) {
    return {
      intent: "Vision / PC local",
      routes: [
        { label: "Lecture ecran", score: 82 },
        { label: "Diagnostic", score: 76 },
        { label: "Action locale", score: 68 },
      ],
      stages: [
        { label: "Comprendre", detail: "Identifier le probleme visible" },
        { label: "Observer", detail: "Lire l'ecran ou le message fourni" },
        { label: "Router", detail: "Choisir diagnostic ou action PC" },
        { label: "Executer", detail: "Appliquer le correctif autorise" },
        { label: "Verifier", detail: "Confirmer que le souci est resolu" },
      ],
    };
  }

  return {
    intent: "Assistant general",
    routes: [
      { label: "Memoire", score: 74 },
      { label: "Ollama", score: 68 },
      { label: "Outil local", score: 54 },
    ],
    stages: [
      { label: "Comprendre", detail: "Interpreter la demande" },
      { label: "Contexte", detail: "Chercher les infos utiles" },
      { label: "Router", detail: "Choisir reponse ou outil" },
      { label: "Executer", detail: "Produire la meilleure action" },
      { label: "Verifier", detail: "Eviter les reponses generiques" },
    ],
  };
}


function ThinkingPipeline({ prompt }) {
  const plan = buildThinkingPlan(prompt);
  const thinkingStages = plan.stages;
  const [activeStage, setActiveStage] = useState(0);

  useEffect(() => {
    setActiveStage(0);
    const timer = window.setInterval(() => {
      setActiveStage((current) => Math.min(current + 1, thinkingStages.length - 1));
    }, 680);

    return () => window.clearInterval(timer);
  }, [prompt, thinkingStages.length]);

  return (
    <div className="thinking-pipeline" aria-label="Eva reflechit">
      <div className="thinking-scan" aria-hidden="true" />
      <div className="thinking-paths" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="thinking-orbit" aria-hidden="true">
        <span />
      </div>
      <div className="thinking-copy">
        <span>Eva reflechit</span>
        <strong>{thinkingStages[activeStage].label}</strong>
        <small>{thinkingStages[activeStage].detail}</small>
      </div>
      <div className="thinking-intent">
        <span>Intention probable</span>
        <strong>{plan.intent}</strong>
      </div>
      <div className="thinking-steps">
        {thinkingStages.map((stage, index) => (
          <div className="thinking-step-node" key={stage.label}>
            <div
              className={`thinking-step ${index < activeStage ? "done" : ""} ${index === activeStage ? "active" : ""}`}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{stage.label}</strong>
            </div>
            {index < thinkingStages.length - 1 && (
              <span
                className={`thinking-arrow ${index < activeStage ? "done" : ""} ${index === activeStage ? "active" : ""}`}
                aria-hidden="true"
              />
            )}
          </div>
        ))}
      </div>
      <div className="thinking-routes">
        {plan.routes.map((route, index) => (
          <div className={index === 0 ? "selected" : ""} key={route.label}>
            <span>{route.label}</span>
            <strong>{route.score}%</strong>
          </div>
        ))}
      </div>
    </div>
  );
}


export function ChatWindow({ messages, loading, error, onStarterSelect, status }) {
  const endRef = useRef(null);
  const latestUserPrompt = [...messages].reverse().find((message) => message.role === "user")?.content || "";
  const isPristine = messages.length === 1 && !loading;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading, error]);

  return (
    <div className="chat-window">
      <div className="messages">
        {isPristine ? (
          <section className="welcome-deck" aria-label="Console Eva">
            <EvaOrb status={status} />

            <div className="welcome-command-panel">
              <div className="welcome-panel-header">
                <span>
                  <Radar size={15} aria-hidden="true" />
                  Centre Eva
                </span>
                <strong>{status?.state === "ready" ? "online" : "sync"}</strong>
              </div>

              <div className="welcome-copy">
                <span>Assistant local de Victor</span>
                <h1>Eva est prete.</h1>
                <p>{messages[0]?.content}</p>
              </div>

              <div className="welcome-signal-grid">
                {deckSignals.map((signal) => (
                  <div key={signal.label}>
                    <span>{signal.label}</span>
                    <strong>{signal.value}</strong>
                  </div>
                ))}
              </div>

              <div className="starter-row" aria-label="Suggestions de depart">
                {starters.map(({ label, prompt, icon: Icon }) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => onStarterSelect(prompt)}
                  >
                    <Icon size={16} aria-hidden="true" />
                    <span>{label}</span>
                    <ArrowUpRight size={15} aria-hidden="true" />
                  </button>
                ))}
              </div>

              <div className="welcome-safety-line">
                <ShieldCheck size={15} aria-hidden="true" />
                <span>Local-first, Ollama, memoire locale, aucune publication sans preuve d'action.</span>
              </div>
            </div>
          </section>
        ) : (
          messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))
        )}

        {loading && (
          <div className="message-row assistant">
            <div className="avatar">E</div>
            <ThinkingPipeline prompt={latestUserPrompt} />
          </div>
        )}

        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
}
