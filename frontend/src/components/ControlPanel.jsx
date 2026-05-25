import { useEffect, useState } from "react";
import {
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Cpu,
  Eye,
  GitBranch,
  HeartPulse,
  Layers3,
  Mail,
  MessagesSquare,
  Network,
  Play,
  RefreshCw,
  Rocket,
  ShieldCheck,
  Terminal,
  Wrench,
} from "lucide-react";

import {
  analyzeScreen,
  getActions,
  getAutonomy,
  getDoctor,
  getGmailMessages,
  getGmailStatus,
  getHealth,
  getHeartbeatStatus,
  getLatestBrief,
  getLinkedInStatus,
  getMemories,
  getObsidianMemoryStatus,
  getProjects,
  getScreenStatus,
  getSkills,
  getTools,
  generateSmartBrief,
  connectGmail,
  openObsidianMemory,
  createGmailReplyDraft,
  createProjectFactoryActions,
  getChatHistory,
  planProjectFactory,
  runGmailAutoReply,
  runHeartbeat,
  syncObsidianMemory,
} from "../api";


const panelMeta = {
  memory: {
    icon: BrainCircuit,
    kicker: "Brain",
    title: "Memoire locale",
    description: "Ce qu'Eva retient localement sur toi, sans token ni mot de passe.",
  },
  chats: {
    icon: MessagesSquare,
    kicker: "Threads",
    title: "Conversations",
    description: "Tes anciens chats web et Telegram archives localement.",
  },
  tools: {
    icon: Wrench,
    kicker: "Hands",
    title: "Tools & permissions",
    description: "Les capacites actives d'Eva et les limites de securite.",
  },
  screen: {
    icon: Eye,
    kicker: "Vision",
    title: "Lecture ecran",
    description: "Capture locale des pixels et interpretation par un modele vision Ollama.",
  },
  skills: {
    icon: Layers3,
    kicker: "Skills",
    title: "Skills Eva",
    description: "Les comportements specialises qui guident Eva selon ta demande.",
  },
  heartbeat: {
    icon: HeartPulse,
    kicker: "Heartbeat",
    title: "Automatisations locales",
    description: "Les jobs planifies qui peuvent tourner sur ton PC quand tu les actives.",
  },
  gmail: {
    icon: Mail,
    kicker: "Mouth",
    title: "Gmail assistant",
    description: "Lecture, brouillons et auto-reponses evidentes si le scope d'envoi est actif.",
  },
  linkedin: {
    icon: Network,
    kicker: "Mouth",
    title: "LinkedIn assistant",
    description: "Brouillons premium, copie presse-papiers et ouverture LinkedIn sans API.",
  },
  projects: {
    icon: GitBranch,
    kicker: "Workspace",
    title: "Projets locaux",
    description: "Les projets qu'Eva connait et peut aider a analyser.",
  },
  brief: {
    icon: Clock3,
    kicker: "Morning",
    title: "Smart Brief",
    description: "Articles lus, score Victor, Gmail/LinkedIn via Gmail si connecte.",
  },
  projectFactory: {
    icon: Rocket,
    kicker: "Factory",
    title: "Project Factory",
    description: "Transforme une idee en workspace local, prompt Cursor et actions validables.",
  },
  actions: {
    icon: Terminal,
    kicker: "Reflexes",
    title: "Actions en attente",
    description: "Les actions sensibles restent bloquees jusqu'a validation humaine.",
  },
  ollama: {
    icon: Cpu,
    kicker: "Core",
    title: "Ollama local",
    description: "Etat du moteur IA gratuit qui fait repondre Eva.",
  },
  doctor: {
    icon: ShieldCheck,
    kicker: "Security",
    title: "Doctor",
    description: "Diagnostic local de la stack Eva.",
  },
};


function statusClass(value) {
  if (value === true || value === "ok" || value === "ready" || value === "executed") return "ok";
  if (value === "read_only" || value === "draft_only") return "ok";
  if (value === false || value === "warning" || value === "pending") return "warning";
  if (value === "confirmation_required") return "warning";
  if (value === "error" || value === "failed" || value === "offline") return "error";
  if (value === "blocked") return "error";
  return "neutral";
}


function StatusPill({ children, tone = "neutral" }) {
  return <span className={`status-pill ${tone}`}>{children}</span>;
}


function mailTone(message) {
  if (message?.is_noise) return "warning";
  if (message?.is_important) return "ok";
  return "neutral";
}


function mailCategoryLabel(message) {
  const category = message?.importance_category || message?.classification?.category || "normal";
  const score = message?.importance_score ?? message?.classification?.importance_score ?? 0;
  return `${category} ${score}/100`;
}


function EmptyState({ children }) {
  return <div className="panel-empty">{children}</div>;
}


function Metric({ label, value, tone = "neutral" }) {
  return (
    <div className={`panel-metric ${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}


function Field({ label, value }) {
  return (
    <div className="panel-field">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}


function renderDoctorChecks(checks = []) {
  if (!checks.length) return <EmptyState>Aucun diagnostic disponible.</EmptyState>;

  return (
    <div className="panel-list">
      {checks.map((check) => (
        <div key={check.name} className="panel-row">
          <div>
            <strong>{check.message}</strong>
            <span>{check.name}</span>
          </div>
          <StatusPill tone={statusClass(check.status)}>{check.status}</StatusPill>
        </div>
      ))}
    </div>
  );
}


export function ControlPanel({ panel, doctor, onPrompt = () => {}, onLoadChatSession = () => {} }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [jobResult, setJobResult] = useState("");
  const [runningJob, setRunningJob] = useState("");
  const [factoryIdea, setFactoryIdea] = useState("");
  const [factoryName, setFactoryName] = useState("");
  const [factoryResult, setFactoryResult] = useState(null);
  const [screenInstruction, setScreenInstruction] = useState("Lis l'ecran et corrige l'erreur visible si le correctif est sur.");
  const [screenResult, setScreenResult] = useState(null);

  const meta = panelMeta[panel] || panelMeta.doctor;
  const Icon = meta.icon;

  async function fetchPanelData(panelName) {
    if (panelName === "memory") {
      const [memory, obsidian] = await Promise.all([getMemories(), getObsidianMemoryStatus()]);
      return { ...memory, obsidian };
    }
    if (panelName === "chats") return getChatHistory();
    if (panelName === "tools") {
      const [tools, autonomy] = await Promise.all([getTools(), getAutonomy()]);
      return { ...tools, autonomy };
    }
    if (panelName === "screen") return getScreenStatus();
    if (panelName === "skills") return getSkills();
    if (panelName === "heartbeat") return getHeartbeatStatus();
    if (panelName === "gmail") {
      const status = await getGmailStatus();
      let messages = [];
      let messagesError = "";
      if (status.enabled && status.credentials_exists && status.token_exists) {
        try {
          const inbox = await getGmailMessages();
          messages = inbox.messages || [];
        } catch (gmailError) {
          messagesError = gmailError.message;
        }
      }
      return { status, messages, messagesError };
    }
    if (panelName === "linkedin") return getLinkedInStatus();
    if (panelName === "projects") return getProjects();
    if (panelName === "brief") return getLatestBrief();
    if (panelName === "projectFactory") return { ready: true };
    if (panelName === "actions") return getActions("pending");
    if (panelName === "ollama") {
      const [health, diagnostic] = await Promise.all([getHealth(), getDoctor()]);
      return { health, diagnostic };
    }
    return getDoctor();
  }

  async function loadPanel() {
    setLoading(true);
    setError("");
    setJobResult("");

    try {
      setData(await fetchPanelData(panel));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;

    async function guardedLoad() {
      setLoading(true);
      setError("");
      setJobResult("");

      try {
        const payload = await fetchPanelData(panel);
        if (active) setData(payload);
      } catch (requestError) {
        if (active) setError(requestError.message);
      } finally {
        if (active) setLoading(false);
      }
    }

    guardedLoad();

    return () => {
      active = false;
    };
  }, [panel]);

  async function handleRunHeartbeat(jobKey) {
    setRunningJob(jobKey);
    setJobResult("");
    setError("");

    try {
      const result = await runHeartbeat(jobKey);
      await loadPanel();
      setJobResult(result.message || "Job execute.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleSyncObsidian() {
    setRunningJob("obsidian_sync");
    setJobResult("");
    setError("");

    try {
      const result = await syncObsidianMemory();
      await loadPanel();
      setJobResult(`${result.synced || 0} souvenirs synchronises dans Obsidian.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleOpenObsidian() {
    setRunningJob("obsidian_open");
    setJobResult("");
    setError("");

    try {
      const result = await openObsidianMemory();
      await loadPanel();
      setJobResult(result.opened ? "Coffre Obsidian Eva ouvert." : "Coffre Obsidian pret.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleGenerateSmartBrief() {
    setRunningJob("smart_brief");
    setJobResult("");
    setError("");

    try {
      const result = await generateSmartBrief();
      setData({ brief: result.brief, smart: result });
      const stats = result.stats || {};
      setJobResult(
        `${stats.articles_read || 0} articles lus, ${stats.gmail_messages || 0} mails, ${stats.linkedin_notifications || 0} signaux LinkedIn.`
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleConnectGmail() {
    setRunningJob("gmail_connect");
    setJobResult("");
    setError("");

    try {
      const status = data?.status || {};
      const needsScopeReconnect = Boolean(status.token_exists && !status.token_has_required_scopes);
      const result = await connectGmail(needsScopeReconnect);
      setJobResult(result.message || "Flux OAuth Gmail lance.");
      await loadPanel();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleCreateGmailDraft(messageId) {
    const jobKey = `gmail_draft_${messageId}`;
    setRunningJob(jobKey);
    setJobResult("");
    setError("");

    try {
      const result = await createGmailReplyDraft(messageId);
      const draft = result.gmail_draft || {};
      setJobResult(
        draft.draft_id
          ? `Brouillon Gmail cree: ${draft.subject || result.subject || "sans objet"}`
          : "Brouillon redige, mais non cree dans Gmail."
      );
      await loadPanel();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleRunGmailAutoReply() {
    setRunningJob("gmail_auto_reply");
    setJobResult("");
    setError("");

    try {
      const result = await runGmailAutoReply(10, false);
      setJobResult(
        `Auto-reponses: ${result.sent_count || 0} envoyee(s), ${result.drafted_count || 0} brouillon(s), ${result.skipped_count || 0} ignoree(s).`
      );
      await loadPanel();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  function renderMemory() {
    const memories = data?.memories || [];
    const obsidian = data?.obsidian || {};

    return (
      <>
        <div className="panel-metrics">
          <Metric label="souvenirs locaux" value={memories.length} tone={memories.length ? "ok" : "neutral"} />
          <Metric label="stockage" value="SQLite" />
          <Metric label="Obsidian" value={obsidian.enabled ? "on" : "off"} tone={obsidian.enabled ? "ok" : "warning"} />
        </div>
        {jobResult && <div className="panel-success">{jobResult}</div>}
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Vault Obsidian local</h3>
            <StatusPill tone={obsidian.exists ? "ok" : "warning"}>{obsidian.exists ? "pret" : "absent"}</StatusPill>
          </div>
          <p>{obsidian.path || "Vault local non configure."}</p>
          <Field label="Fichiers Markdown" value={obsidian.markdown_files || 0} />
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button primary"
              onClick={handleOpenObsidian}
              disabled={Boolean(runningJob)}
            >
              {runningJob === "obsidian_open" ? "Ouverture..." : "Ouvrir le coffre"}
            </button>
            <button
              type="button"
              className="panel-action-button"
              onClick={handleSyncObsidian}
              disabled={Boolean(runningJob)}
            >
              {runningJob === "obsidian_sync" ? "Synchronisation..." : "Synchroniser Obsidian"}
            </button>
          </div>
        </section>
        {memories.length ? (
          <div className="panel-list">
            {memories.map((memory) => (
              <div key={memory.id} className="panel-row">
                <div>
                  <strong>{memory.content}</strong>
                  <span>{memory.category} / {memory.source} / confiance {Math.round(memory.confidence * 100)}%</span>
                </div>
                <StatusPill>{`#${memory.id}`}</StatusPill>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState>Eva n'a pas encore de souvenirs locaux. Dis-lui "Eva, retiens que..." pour ajouter une information non sensible.</EmptyState>
        )}
      </>
    );
  }

  function renderChats() {
    const sessions = data?.sessions || [];
    const webCount = sessions.filter((session) => session.channel === "web").length;
    const telegramCount = sessions.filter((session) => session.channel === "telegram").length;

    return (
      <>
        <div className="panel-metrics">
          <Metric label="conversations" value={sessions.length} tone={sessions.length ? "ok" : "neutral"} />
          <Metric label="web" value={webCount} />
          <Metric label="telegram" value={telegramCount} tone={telegramCount ? "ok" : "neutral"} />
        </div>
        {sessions.length ? (
          <div className="panel-list">
            {sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                className="panel-row panel-row-button"
                onClick={() => onLoadChatSession(session.id)}
              >
                <div>
                  <strong>{session.title || "Conversation Eva"}</strong>
                  <span>{session.channel} / {session.updated_at}</span>
                </div>
                <StatusPill tone={session.channel === "telegram" ? "ok" : "neutral"}>
                  {session.channel}
                </StatusPill>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState>Aucune conversation archivee pour le moment.</EmptyState>
        )}
      </>
    );
  }

  function renderTools() {
    const tools = data?.tools || [];
    const autonomy = data?.autonomy || {};

    return (
      <>
        <div className="panel-grid">
          <section className="panel-card">
            <h3>Sans confirmation</h3>
            <div className="panel-chip-list">
              {(autonomy.safe_without_confirmation || []).map((item) => (
                <StatusPill key={item} tone="ok">{item}</StatusPill>
              ))}
            </div>
          </section>
          <section className="panel-card">
            <h3>Validation obligatoire</h3>
            <div className="panel-chip-list">
              {(autonomy.requires_confirmation || []).map((item) => (
                <StatusPill key={item} tone="warning">{item}</StatusPill>
              ))}
            </div>
          </section>
        </div>
        <div className="panel-list">
          {tools.map((tool) => (
            <div key={tool.key} className="panel-row">
              <div>
                <strong>{tool.label}</strong>
                <span>{tool.description}</span>
              </div>
              <StatusPill tone={statusClass(tool.policy_level)}>{tool.policy_level}</StatusPill>
            </div>
          ))}
        </div>
      </>
    );
  }

  async function handleAnalyzeScreen() {
    setRunningJob("screen_analyze");
    setScreenResult(null);
    setError("");

    try {
      const result = await analyzeScreen(screenInstruction, true);
      setScreenResult(result);
      setJobResult("Ecran analyse localement.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  function renderScreen() {
    const terminalDiagnosis = screenResult?.terminal_diagnosis || {};
    const launched = screenResult?.launched;

    return (
      <>
        <div className="panel-metrics">
          <Metric label="lecture ecran" value={data?.enabled ? "on" : "off"} tone={data?.enabled ? "ok" : "warning"} />
          <Metric label="Pillow" value={data?.pillow_available ? "pret" : "absent"} tone={data?.pillow_available ? "ok" : "warning"} />
          <Metric label="modele vision" value={data?.vision_model || "llava:7b"} />
        </div>
        <section className="panel-card">
          <h3>Analyse des pixels</h3>
          <p>Eva capture l'ecran local, l'envoie a Ollama local, puis interprete ce qui est visible. Les captures restent dans data/screen_captures et sont ignorees par Git.</p>
          <textarea
            className="panel-textarea"
            value={screenInstruction}
            onChange={(event) => setScreenInstruction(event.target.value)}
            rows={4}
          />
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button"
              onClick={handleAnalyzeScreen}
              disabled={Boolean(runningJob)}
            >
              {runningJob === "screen_analyze" ? "Analyse..." : "Analyser ecran"}
            </button>
          </div>
          <Field label="Captures" value={data?.capture_dir || "data/screen_captures"} />
        </section>
        {jobResult && <div className="panel-success">{jobResult}</div>}
        {screenResult && (
          <section className="panel-card">
            <div className="panel-card-heading">
              <h3>Resultat</h3>
              <StatusPill tone={terminalDiagnosis.detected ? "warning" : "ok"}>
                {terminalDiagnosis.detected ? "erreur detectee" : "analyse"}
              </StatusPill>
            </div>
            <p>{screenResult.analysis}</p>
            {terminalDiagnosis.detected && <Field label="Terminal Doctor" value={terminalDiagnosis.title} />}
            {launched && <Field label="Action lancee" value={launched.message} />}
          </section>
        )}
      </>
    );
  }

  function renderSkills() {
    const skills = data?.skills || [];
    const categories = new Set(skills.map((skill) => skill.category));
    const enabledSkills = skills.filter((skill) => skill.enabled !== false);
    const skillpacks = skills.filter((skill) => skill.extension_type === "skillpack");

    return (
      <>
        <div className="panel-metrics">
          <Metric label="skills actives" value={enabledSkills.length} tone={enabledSkills.length ? "ok" : "warning"} />
          <Metric label="categories" value={categories.size} />
          <Metric label="skillpacks" value={skillpacks.length} tone={skillpacks.length ? "ok" : "neutral"} />
        </div>
        <div className="panel-grid">
          {skills.map((skill) => (
            <section
              key={skill.key}
              className={`panel-card skill-card ${skill.extension_type === "skillpack" ? "skill-card-pack" : ""}`}
            >
              <div className="panel-card-heading">
                <h3>{skill.label}</h3>
                <StatusPill tone={statusClass(skill.policy_level)}>{skill.policy_level}</StatusPill>
              </div>
              <p>{skill.description}</p>
              <div className="skill-card-meta">
                <Field label="Categorie" value={skill.category} />
                <Field label="Source" value={skill.source || "core"} />
                <Field label="Statut" value={skill.status || "active"} />
                {skill.extension_type && <Field label="Extension" value={skill.extension_type} />}
              </div>
              {skill.instructions && (
                <div className="skill-instructions">
                  <strong>Methode</strong>
                  <span>{skill.instructions.slice(0, 260)}{skill.instructions.length > 260 ? "..." : ""}</span>
                </div>
              )}
              <div className="panel-chip-list">
                {(skill.trigger_words || []).slice(0, 6).map((trigger) => (
                  <StatusPill key={trigger}>{trigger}</StatusPill>
                ))}
              </div>
              {(skill.tool_hints || []).length > 0 && (
                <div className="panel-chip-list tool-chip-list">
                  {(skill.tool_hints || []).slice(0, 5).map((tool) => (
                    <StatusPill key={tool} tone="ok">{tool}</StatusPill>
                  ))}
                </div>
              )}
              {(skill.next_steps || []).length > 0 && (
                <Field label="Prochaine etape" value={(skill.next_steps || []).slice(0, 2).join(" | ")} />
              )}
            </section>
          ))}
        </div>
      </>
    );
  }

  function renderHeartbeat() {
    const jobs = data?.jobs || [];
    const state = data?.enabled ? "Actif" : "Desactive";

    return (
      <>
        <div className="panel-metrics">
          <Metric label="etat global" value={state} tone={data?.enabled ? "ok" : "warning"} />
          <Metric label="jobs configures" value={jobs.length} />
          <Metric label="poll" value={`${data?.poll_seconds || 0}s`} />
        </div>
        {jobResult && <div className="panel-success">{jobResult}</div>}
        <div className="panel-grid">
          {jobs.map((job) => (
            <section key={job.key} className="panel-card">
              <div className="panel-card-heading">
                <h3>{job.label}</h3>
                <StatusPill tone={job.enabled ? "ok" : "warning"}>{job.enabled ? "active" : "off"}</StatusPill>
              </div>
              <p>{job.description}</p>
              <Field label="Heure" value={job.time || "manuel"} />
              <button
                type="button"
                className="panel-action-button"
                onClick={() => handleRunHeartbeat(job.key)}
                disabled={Boolean(runningJob)}
              >
                <Play size={15} aria-hidden="true" />
                {runningJob === job.key ? "Execution..." : "Executer maintenant"}
              </button>
            </section>
          ))}
        </div>
      </>
    );
  }

  function renderGmail() {
    const status = data?.status || {};
    const messages = data?.messages || [];

    return (
      <>
        <div className="panel-metrics">
          <Metric label="integration" value={status.enabled ? "active" : "off"} tone={status.enabled ? "ok" : "warning"} />
          <Metric label="OAuth token" value={status.token_exists ? "connecte" : "absent"} tone={status.token_exists ? "ok" : "warning"} />
          <Metric label="brouillons" value={status.can_create_drafts ? "actifs" : "scope"} tone={status.can_create_drafts ? "ok" : "warning"} />
          <Metric label="scope send" value={status.can_send ? "ok" : "manquant"} tone={status.can_send ? "ok" : "warning"} />
          <Metric label="auto-reponse" value={status.can_auto_send_obvious_replies ? "active" : "off"} tone={status.can_auto_send_obvious_replies ? "warning" : "neutral"} />
        </div>
        {!status.token_exists && (
          <div className="panel-empty">
            Gmail est configure, mais Google n'a pas encore donne de token local a Eva. Lance la connexion, valide dans Google, puis rafraichis ce panneau.
          </div>
        )}
        {jobResult && <div className="panel-success">{jobResult}</div>}
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Connexion OAuth locale</h3>
            <StatusPill tone={status.token_exists ? "ok" : "warning"}>
              {status.token_exists ? "connecte" : "a connecter"}
            </StatusPill>
          </div>
          <p>Eva ouvre Google dans ton navigateur. Tu valides Gmail lecture, brouillons, envoi encadre et Calendar lecture.</p>
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button"
              onClick={handleConnectGmail}
              disabled={Boolean(runningJob) || !status.enabled || !status.credentials_exists || (status.token_exists && status.token_has_required_scopes)}
            >
              {runningJob === "gmail_connect" ? "Ouverture..." : status.token_exists ? "Completer scopes" : "Connecter Gmail"}
            </button>
            <button type="button" className="panel-action-button secondary" onClick={loadPanel}>
              Rafraichir statut
            </button>
            {status.token_exists && !status.token_has_required_scopes && (
              <button
                type="button"
                className="panel-action-button"
                onClick={() => connectGmail(true).then((result) => {
                  setJobResult(result.message || "Reconnexion Google lancee.");
                  return loadPanel();
                }).catch((requestError) => setError(requestError.message))}
                disabled={Boolean(runningJob)}
              >
                Reconnecter scopes
              </button>
            )}
          </div>
          {!status.enabled && <p>Active EVA_GMAIL_ENABLED=true dans backend/.env.</p>}
          {!status.credentials_exists && <p>Ajoute le JSON OAuth complet dans data/gmail_credentials.json.</p>}
          {status.token_exists && !status.can_send && (
            <p>Le scope gmail.send manque encore. Clique Reconnecter scopes avant les auto-reponses.</p>
          )}
        </section>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Auto-reponses evidentes</h3>
            <StatusPill tone={status.can_auto_send_obvious_replies ? "warning" : "neutral"}>
              {status.can_auto_send_obvious_replies ? "active" : "protege"}
            </StatusPill>
          </div>
          <p>Eva envoie seule uniquement si le mail est non sensible, dans la bonne langue, deja similaire a tes reponses passees et au-dessus du seuil de confiance.</p>
          <Field label="Recherche" value={status.auto_reply_query || "inbox"} />
          <Field label="Seuil" value={`${Math.round((status.auto_reply_min_confidence || 0) * 100)}%`} />
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button"
              onClick={handleRunGmailAutoReply}
              disabled={Boolean(runningJob) || !status.can_auto_send_obvious_replies}
            >
              <Play size={15} aria-hidden="true" />
              {runningJob === "gmail_auto_reply" ? "Analyse..." : "Lancer maintenant"}
            </button>
          </div>
          {!status.auto_external_send_allowed && <p>Active EVA_ALLOW_AUTO_EXTERNAL_SEND=true dans backend/.env pour autoriser ce mode.</p>}
        </section>
        {data?.messagesError && <div className="panel-error">{data.messagesError}</div>}
        {messages.length ? (
          <div className="panel-list">
            {messages.map((message) => (
              <div key={message.id} className={`panel-row ${message.is_noise ? "muted-row" : ""}`}>
                <div>
                  <strong>{message.subject || "Sans objet"}</strong>
                  <span>{message.from || message.sender_email || "Expediteur inconnu"}</span>
                  {message.classification_reason && (
                    <span className="panel-row-note">{message.classification_reason}</span>
                  )}
                </div>
                <div className="panel-row-actions">
                  <button
                    type="button"
                    className="panel-mini-button"
                    onClick={() => handleCreateGmailDraft(message.id)}
                    disabled={Boolean(runningJob) || !status.can_create_drafts}
                  >
                    {runningJob === `gmail_draft_${message.id}` ? "Creation..." : "Brouillon"}
                  </button>
                  <StatusPill tone={mailTone(message)}>{mailCategoryLabel(message)}</StatusPill>
                  <StatusPill>{message.date || "inbox"}</StatusPill>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </>
    );
  }

  function renderLinkedIn() {
    return (
      <>
        <div className="panel-metrics">
          <Metric label="assistant" value={data?.enabled ? "actif" : "off"} tone={data?.enabled ? "ok" : "warning"} />
          <Metric label="mode" value={data?.mode || "draft_only"} tone="ok" />
          <Metric label="navigateur" value={data?.can_prepare_browser_post ? "pret" : "off"} tone={data?.can_prepare_browser_post ? "ok" : "warning"} />
        </div>
        <section className="panel-card">
          <h3>Profil connu</h3>
          <p>{data?.profile_url || "Aucun profil LinkedIn local configure."}</p>
          {data?.company_page_url && <p>{data.company_page_url}</p>}
          <p>{data?.note || "Eva prepare uniquement des brouillons."}</p>
          <div className="panel-actions">
            <button type="button" className="panel-action-button" onClick={() => onPrompt("Fais un post LinkedIn pertinent pour DreamLense et ouvre LinkedIn dans le navigateur.")}>
              Preparer et ouvrir LinkedIn
            </button>
            <button type="button" className="panel-action-button" onClick={() => onPrompt("Prepare 3 idees de posts LinkedIn pour DreamLense cette semaine.")}>
              Idees de posts
            </button>
            <button type="button" className="panel-action-button secondary" onClick={() => onPrompt("Prepare une relance LinkedIn courte pour un prospect DreamLense.")}>
              Relance prospect
            </button>
          </div>
        </section>
      </>
    );
  }

  function renderProjects() {
    const projects = data?.projects || [];

    return projects.length ? (
      <div className="panel-grid">
        {projects.map((project) => (
          <section key={project.name} className="panel-card">
            <div className="panel-card-heading">
              <h3>{project.name}</h3>
              <StatusPill>{project.type || "code"}</StatusPill>
            </div>
            <p>{project.description || "Projet local"}</p>
            <Field label="Chemin" value={project.path} />
            <button
              type="button"
              className="panel-action-button"
              onClick={() => onPrompt(`Prepare un plan de travail Cursor pour le projet ${project.name}.`)}
            >
              Prompt Cursor
            </button>
          </section>
        ))}
      </div>
    ) : (
      <EmptyState>Aucun projet local configure.</EmptyState>
    );
  }

  function renderBrief() {
    const brief = data?.brief;
    const smart = data?.smart;
    const stats = smart?.stats || {};

    return (
      <>
        {smart && (
          <div className="panel-metrics">
            <Metric label="articles lus" value={stats.articles_read || 0} tone={stats.articles_read ? "ok" : "warning"} />
            <Metric label="mails" value={stats.gmail_messages || 0} tone={stats.gmail_messages ? "ok" : "neutral"} />
            <Metric label="LinkedIn via Gmail" value={stats.linkedin_notifications || 0} tone={stats.linkedin_notifications ? "ok" : "neutral"} />
          </div>
        )}
        {jobResult && <div className="panel-success">{jobResult}</div>}
        <section className="panel-card">
          <h3>{brief?.title || "Aucun Smart Brief cree pour le moment"}</h3>
          <p>{brief?.content || "Eva peut lire les RSS, ouvrir les articles utiles, scorer les infos pour Victor et ajouter Gmail/LinkedIn via Gmail si connecte."}</p>
          {brief?.created_at && <Field label="Cree le" value={brief.created_at} />}
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button"
              onClick={handleGenerateSmartBrief}
              disabled={Boolean(runningJob)}
            >
              {runningJob === "smart_brief" ? "Lecture en cours..." : "Generer Smart Brief"}
            </button>
            <button type="button" className="panel-action-button" onClick={() => onPrompt("Prepare mon brief du matin business, tech, IA, finance et DreamLense.")}>
              Preparer dans le chat
            </button>
          </div>
        </section>
        {brief?.items?.length ? (
          <div className="panel-list">
            {brief.items.slice(0, 8).map((item, index) => (
              <div key={`${item.url || item.title}-${index}`} className="panel-row">
                <div>
                  <strong>{item.title || "Source"}</strong>
                  <span>
                    {item.source || item.url || "RSS"}
                    {item.victor_score ? ` / score ${item.victor_score}` : ""}
                    {item.article_read ? " / article lu" : ""}
                  </span>
                </div>
                {item.victor_tags?.length ? <StatusPill tone="ok">{item.victor_tags.slice(0, 2).join(", ")}</StatusPill> : null}
              </div>
            ))}
          </div>
        ) : null}
      </>
    );
  }

  async function handleProjectFactoryPlan() {
    const idea = factoryIdea.trim();
    if (!idea) return;
    setRunningJob("project_factory_plan");
    setFactoryResult(null);
    setError("");
    try {
      setFactoryResult(await planProjectFactory(idea, factoryName.trim()));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleProjectFactoryActions() {
    const idea = factoryIdea.trim();
    if (!idea) return;
    setRunningJob("project_factory_actions");
    setFactoryResult(null);
    setError("");
    try {
      setFactoryResult(await createProjectFactoryActions(idea, factoryName.trim()));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  function renderProjectFactory() {
    const plan = factoryResult?.plan;
    const actions = factoryResult?.actions || [];

    return (
      <>
        <section className="panel-card">
          <h3>Nouvelle idee projet</h3>
          <input
            className="panel-input"
            value={factoryName}
            onChange={(event) => setFactoryName(event.target.value)}
            placeholder="Nom du projet optionnel"
          />
          <textarea
            className="panel-textarea"
            value={factoryIdea}
            onChange={(event) => setFactoryIdea(event.target.value)}
            placeholder="Decris l'idee, le produit, la cible, la stack ou le resultat attendu..."
            rows={6}
          />
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button secondary"
              onClick={handleProjectFactoryPlan}
              disabled={Boolean(runningJob)}
            >
              Previsualiser
            </button>
            <button
              type="button"
              className="panel-action-button"
              onClick={handleProjectFactoryActions}
              disabled={Boolean(runningJob)}
            >
              Creer actions
            </button>
          </div>
        </section>

        {plan && (
          <>
            <div className="panel-metrics">
              <Metric label="projet" value={plan.project_name} tone="ok" />
              <Metric label="template" value={plan.stack?.template || "local"} />
              <Metric label="actions" value={actions.length || "preview"} tone={actions.length ? "warning" : "neutral"} />
            </div>
            <section className="panel-card">
              <h3>Plan local</h3>
              <p>{plan.idea}</p>
              <Field label="Dossier cible" value={plan.workspace_path} />
              <Field label="Repo GitHub propose" value={plan.repo_name} />
              <Field label="Cursor" value="CURSOR_PROMPT.md sera cree localement." />
            </section>
            <div className="panel-list">
              {Object.keys(plan.files || {}).map((fileName) => (
                <div key={fileName} className="panel-row">
                  <div>
                    <strong>{fileName}</strong>
                    <span>Fichier prepare par Eva</span>
                  </div>
                  <StatusPill tone="warning">validation</StatusPill>
                </div>
              ))}
            </div>
          </>
        )}

        {actions.length > 0 && (
          <div className="panel-list">
            {actions.map((action) => (
              <div key={action.id} className="panel-row">
                <div>
                  <strong>#{action.id} {action.title}</strong>
                  <span>{action.description}</span>
                </div>
                <StatusPill tone="warning">{action.status}</StatusPill>
              </div>
            ))}
          </div>
        )}
      </>
    );
  }

  function renderActions() {
    const actions = data?.actions || [];

    return actions.length ? (
      <div className="panel-list">
        {actions.map((action) => (
          <div key={action.id} className="panel-row">
            <div>
              <strong>{action.title}</strong>
              <span>{action.description || action.action_type}</span>
            </div>
            <StatusPill tone={statusClass(action.status)}>{action.status}</StatusPill>
          </div>
        ))}
      </div>
    ) : (
      <EmptyState>Aucune action sensible en attente. C'est exactement le comportement voulu.</EmptyState>
    );
  }

  function renderOllama() {
    const diagnostic = data?.diagnostic || doctor;
    const modelCheck = diagnostic?.checks?.find((check) => check.name === "ollama_model_available");

    return (
      <>
        <div className="panel-metrics">
          <Metric label="backend" value={data?.health?.status || "ok"} tone="ok" />
          <Metric label="modele" value={data?.health?.model || "local"} />
          <Metric label="doctor" value={diagnostic?.status || "scan"} tone={statusClass(diagnostic?.status)} />
        </div>
        <section className="panel-card">
          <h3>Modele Ollama</h3>
          <p>{modelCheck?.message || "Eva utilise Ollama local pour rester gratuite."}</p>
        </section>
      </>
    );
  }

  function renderDoctor() {
    const diagnostic = data || doctor;

    return (
      <>
        <div className="panel-metrics">
          <Metric label="statut" value={diagnostic?.status || "scan"} tone={statusClass(diagnostic?.status)} />
          <Metric label="checks" value={diagnostic?.checks?.length || 0} />
          <Metric label="mode" value="local" tone="ok" />
        </div>
        <section className="panel-card">
          <h3>Resume</h3>
          <p>{diagnostic?.summary || "Diagnostic en cours."}</p>
        </section>
        {renderDoctorChecks(diagnostic?.checks)}
      </>
    );
  }

  function renderBody() {
    if (loading) return <div className="panel-loading">Chargement du module Eva...</div>;
    if (error) return <div className="panel-error">{error}</div>;
    if (panel === "memory") return renderMemory();
    if (panel === "chats") return renderChats();
    if (panel === "tools") return renderTools();
    if (panel === "screen") return renderScreen();
    if (panel === "skills") return renderSkills();
    if (panel === "heartbeat") return renderHeartbeat();
    if (panel === "gmail") return renderGmail();
    if (panel === "linkedin") return renderLinkedIn();
    if (panel === "projects") return renderProjects();
    if (panel === "brief") return renderBrief();
    if (panel === "projectFactory") return renderProjectFactory();
    if (panel === "actions") return renderActions();
    if (panel === "ollama") return renderOllama();
    return renderDoctor();
  }

  return (
    <div className="panel-window">
      <div className="control-panel">
        <header className="panel-hero">
          <div className="panel-hero-icon">
            <Icon size={24} aria-hidden="true" />
          </div>
          <div>
            <span className="eyebrow">{meta.kicker}</span>
            <h2>{meta.title}</h2>
            <p>{meta.description}</p>
          </div>
          <button type="button" className="panel-refresh" onClick={loadPanel} aria-label="Rafraichir">
            <RefreshCw size={17} aria-hidden="true" />
          </button>
        </header>
        {renderBody()}
      </div>
    </div>
  );
}
