import { useEffect, useState } from "react";
import {
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Crown,
  Cpu,
  Eye,
  GitBranch,
  HeartPulse,
  Layers3,
  ListChecks,
  Mail,
  MessagesSquare,
  Network,
  Play,
  RefreshCw,
  Route,
  Rocket,
  ShieldCheck,
  Terminal,
  TrendingUp,
  Wrench,
} from "lucide-react";

import {
  analyzeScreen,
  consolidateMemoryLearning,
  createAutonomyJob,
  getActions,
  getAutonomy,
  getCuriosityStatus,
  getDoctor,
  getGmailMessages,
  getGmailStatus,
  getHealth,
  getHeartbeatStatus,
  getJobs,
  getJobsStatus,
  getKnowledgeStatus,
  getLatestBrief,
  getLinkedInStatus,
  getMemories,
  getMemoryEmbeddingStatus,
  getMemoryLearningStatus,
  getMlAdaptationStatus,
  getObsidianMemoryStatus,
  getProjects,
  getReinforcementStatus,
  getResolverStatus,
  getRoles,
  getScreenStatus,
  getSkills,
  getTools,
  generateSmartBrief,
  hydrateObsidianMemory,
  importObsidianMemory,
  importMachineLearningKnowledge,
  rebuildMemoryEmbeddings,
  connectGmail,
  openObsidianMemory,
  organizeObsidianMemory,
  createGmailReplyDraft,
  createProjectFactoryActions,
  getChatHistory,
  planProjectFactory,
  runGmailAutoReply,
  runHeartbeat,
  runCuriosity,
  runNextAutonomyJob,
  seedObsidianMemory,
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
  roles: {
    icon: Crown,
    kicker: "Command Deck",
    title: "Roles internes",
    description: "Les casquettes qu'Eva active avant de comprendre, planifier et agir.",
  },
  heartbeat: {
    icon: HeartPulse,
    kicker: "Heartbeat",
    title: "Automatisations locales",
    description: "Les jobs planifies qui peuvent tourner sur ton PC quand tu les actives.",
  },
  curiosity: {
    icon: BookOpen,
    kicker: "Curiosity",
    title: "Apprentissage autonome",
    description: "Eva lit des sources publiques, filtre ce qui sert Victor, puis enrichit la memoire.",
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
  jobs: {
    icon: ListChecks,
    kicker: "Autonomy",
    title: "Jobs autonomes",
    description: "Queue locale un par un avec resultats, checkpoints JSONL et reprise au redemarrage.",
  },
  actions: {
    icon: Terminal,
    kicker: "Reflexes",
    title: "Actions en attente",
    description: "Les actions sensibles restent bloquees jusqu'a validation humaine.",
  },
  resolver: {
    icon: Route,
    kicker: "Resolver",
    title: "Resolution de problemes",
    description: "Les blocages deviennent diagnostics, plans B et traces locales exploitables.",
  },
  reinforcement: {
    icon: TrendingUp,
    kicker: "Learning",
    title: "Rewards locaux",
    description: "Bonus/malus qui apprennent a Eva quelles routes marchent vraiment.",
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
  if (value === "completed" || value === "running") return "ok";
  if (value === "read_only" || value === "draft_only") return "ok";
  if (value === "queued") return "warning";
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


function rewardTone(value = 0) {
  if (value > 0.2) return "ok";
  if (value < -0.2) return "error";
  return "neutral";
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
    <div className="doctor-check-grid">
      {checks.map((check) => (
        <div key={check.name} className={`doctor-check-card ${statusClass(check.status)}`}>
          <span>{check.name}</span>
          <strong>{check.message}</strong>
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
  const [autonomyJobInstruction, setAutonomyJobInstruction] = useState("");

  const meta = panelMeta[panel] || panelMeta.doctor;
  const Icon = meta.icon;

  async function fetchPanelData(panelName) {
    if (panelName === "memory") {
      const [memory, obsidian, embeddings, learning, knowledge, mlAdaptation] = await Promise.all([
        getMemories(),
        getObsidianMemoryStatus(),
        getMemoryEmbeddingStatus(),
        getMemoryLearningStatus(),
        getKnowledgeStatus(),
        getMlAdaptationStatus(40),
      ]);
      return { ...memory, obsidian, embeddings, learning, knowledge, mlAdaptation };
    }
    if (panelName === "chats") return getChatHistory();
    if (panelName === "tools") {
      const [tools, autonomy] = await Promise.all([getTools(), getAutonomy()]);
      return { ...tools, autonomy };
    }
    if (panelName === "screen") return getScreenStatus();
    if (panelName === "skills") return getSkills();
    if (panelName === "roles") return getRoles();
    if (panelName === "heartbeat") return getHeartbeatStatus();
    if (panelName === "curiosity") return getCuriosityStatus(30);
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
    if (panelName === "jobs") {
      const [jobs, runner] = await Promise.all([getJobs(40), getJobsStatus()]);
      return { ...jobs, runner };
    }
    if (panelName === "actions") return getActions("pending");
    if (panelName === "resolver") return getResolverStatus(30);
    if (panelName === "reinforcement") return getReinforcementStatus(40);
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

  async function handleRunCuriosity() {
    setRunningJob("curiosity_run");
    setJobResult("");
    setError("");

    try {
      const result = await runCuriosity(true);
      await loadPanel();
      setJobResult(
        `${result.learned?.length || 0} apprentissage(s) ajoute(s) depuis ${result.candidates || 0} source(s) candidates.`
      );
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

  async function handleHydrateObsidian() {
    setRunningJob("obsidian_hydrate");
    setJobResult("");
    setError("");

    try {
      const result = await hydrateObsidianMemory();
      await loadPanel();
      setJobResult(`${result.markdown_files || 0} notes Obsidian pretes pour Eva.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleOrganizeObsidian() {
    setRunningJob("obsidian_organize");
    setJobResult("");
    setError("");

    try {
      const result = await organizeObsidianMemory();
      await loadPanel();
      const moved = result.moved?.length ? ` ${result.moved.length} note(s) racine rangee(s).` : "";
      setJobResult(`${result.written_count || 0} index Obsidian mis a jour.${moved}`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleImportObsidian() {
    setRunningJob("obsidian_import");
    setJobResult("");
    setError("");

    try {
      const result = await importObsidianMemory(400);
      await loadPanel();
      const embeddingStatus = result.embeddings?.rebuilt ? " Embeddings reconstruits." : "";
      const failures = result.failed ? ` ${result.failed} ligne(s) ignoree(s).` : "";
      setJobResult(
        `${result.imported || 0} souvenir(s) importes depuis ${result.scanned_files || 0} note(s) Obsidian.${failures}${embeddingStatus}`
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleSeedObsidian() {
    setRunningJob("obsidian_seed");
    setJobResult("");
    setError("");

    try {
      const result = await seedObsidianMemory(700, true);
      await loadPanel();
      const imported = result.import?.imported || 0;
      const vectors = result.import?.embeddings?.rebuilt ? " Embeddings reconstruits." : "";
      const existing = result.existing ? ` ${result.existing} note(s) deja presentes.` : "";
      setJobResult(
        `${result.seeded || 0} note(s) de base ajoutee(s), ${imported} souvenir(s) importes depuis Obsidian.${existing}${vectors}`
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleImportKnowledge() {
    setRunningJob("knowledge_import");
    setJobResult("");
    setError("");

    try {
      const result = await importMachineLearningKnowledge({
        limit: 20,
        maxPages: 18,
        importToSqlite: true,
        writeObsidian: true,
        rebuildEmbeddings: false,
        replaceExisting: true,
      });
      await loadPanel();
      const errors = result.errors?.length ? ` ${result.errors.length} erreur(s) a verifier.` : "";
      setJobResult(
        `${result.imported_documents || 0} PDF(s) ML indexes, ${result.imported_memories || 0} souvenir(s) ajoutes.${errors}`
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleRebuildEmbeddings() {
    setRunningJob("embeddings_rebuild");
    setJobResult("");
    setError("");

    try {
      const result = await rebuildMemoryEmbeddings(400);
      await loadPanel();
      const errors = (result.errors || []).length ? ` Erreurs: ${result.errors.join(" | ")}` : "";
      setJobResult(`${result.indexed || 0} souvenirs indexes en vectoriel, ${result.failed || 0} echec(s).${errors}`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleConsolidateLearning() {
    setRunningJob("memory_learning");
    setJobResult("");
    setError("");

    try {
      const result = await consolidateMemoryLearning(160, true);
      await loadPanel();
      const clusterText = (result.clusters || [])
        .slice(0, 3)
        .map((cluster) => `${cluster.label}: ${cluster.count}`)
        .join(" / ");
      const suffix = clusterText ? ` Clusters: ${clusterText}.` : "";
      setJobResult(
        `${result.stored || 0} apprentissage(s) consolide(s) depuis ${result.ticks_analyzed || 0} tick(s).${suffix}`
      );
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
      const needsScopeReconnect = Boolean(status.token_exists);
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
    const embeddings = data?.embeddings || {};
    const learning = data?.learning || {};
    const knowledge = data?.knowledge || {};
    const mlAdaptation = data?.mlAdaptation || {};
    const embeddingCount = embeddings.embedding_count || 0;
    const memoryCount = embeddings.memory_count ?? memories.length;

    return (
      <>
        <div className="panel-metrics">
          <Metric label="souvenirs locaux" value={memories.length} tone={memories.length ? "ok" : "neutral"} />
          <Metric
            label="vecteurs"
            value={`${embeddingCount}/${memoryCount}`}
            tone={memoryCount && embeddingCount < memoryCount ? "warning" : "ok"}
          />
          <Metric label="Obsidian" value={obsidian.enabled ? "on" : "off"} tone={obsidian.enabled ? "ok" : "warning"} />
          <Metric
            label="apprentissages"
            value={learning.learning_memories || 0}
            tone={learning.learning_memories ? "ok" : "neutral"}
          />
          <Metric
            label="PDF ML"
            value={knowledge.pdf_count || 0}
            tone={knowledge.pdf_count ? "ok" : "neutral"}
          />
          <Metric
            label="policy ML"
            value={mlAdaptation.enabled ? "active" : "off"}
            tone={mlAdaptation.enabled ? "ok" : "warning"}
          />
        </div>
        {jobResult && <div className="panel-success">{jobResult}</div>}
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Boucle d'apprentissage locale</h3>
            <StatusPill tone={learning.enabled ? "ok" : "warning"}>{learning.enabled ? "active" : "off"}</StatusPill>
          </div>
          <p>
            Eva extrait les lecons stables de ses echanges, les classe en clusters,
            les ajoute a SQLite, les miroir dans Obsidian et peut reconstruire les embeddings.
          </p>
          <Field label="Ticks operateur" value={learning.operator_ticks || 0} />
          <Field label="A reprendre" value={learning.needs_followup || 0} />
          <Field label="Rapports Obsidian" value={learning.report_count || 0} />
          {learning.clusters?.length ? (
            <div className="panel-chip-list">
              {learning.clusters.slice(0, 6).map((cluster) => (
                <StatusPill key={cluster.key} tone="ok">
                  {cluster.label} {cluster.count}
                </StatusPill>
              ))}
            </div>
          ) : null}
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button primary"
              onClick={handleConsolidateLearning}
              disabled={Boolean(runningJob) || !learning.enabled}
            >
              {runningJob === "memory_learning" ? "Consolidation..." : "Apprendre des echanges"}
            </button>
          </div>
        </section>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Connaissances Machine Learning</h3>
            <StatusPill tone={knowledge.pdf_reader_available ? "ok" : "warning"}>
              {knowledge.pdf_reader_available ? "PDF ready" : "pypdf absent"}
            </StatusPill>
          </div>
          <p>
            Eva transforme tes supports ML locaux en notes Obsidian, souvenirs SQLite et contexte vectoriel.
            Elle s'en sert ensuite pour mieux choisir ses routes, clusters, rewards et corrections.
          </p>
          <Field label="Dossier" value={knowledge.source_dir || "docs"} />
          <Field label="PDF detectes" value={knowledge.pdf_count || 0} />
          <Field label="Notes knowledge" value={knowledge.knowledge_notes || 0} />
          <Field label="Souvenirs ML" value={knowledge.knowledge_memories || 0} />
          {knowledge.pdfs?.length ? (
            <div className="panel-chip-list">
              {knowledge.pdfs.slice(0, 6).map((pdf) => (
                <StatusPill key={pdf.name}>{pdf.name.replace(/^CX016-2\.5-3-IML - /, "")}</StatusPill>
              ))}
            </div>
          ) : null}
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button primary"
              onClick={handleImportKnowledge}
              disabled={Boolean(runningJob) || !knowledge.pdf_reader_available || !knowledge.pdf_count}
            >
              {runningJob === "knowledge_import" ? "Import ML..." : "Importer PDFs ML"}
            </button>
          </div>
        </section>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Adaptation ML en production</h3>
            <StatusPill tone={mlAdaptation.enabled ? "ok" : "warning"}>
              {mlAdaptation.enabled ? "branchee" : "off"}
            </StatusPill>
          </div>
          <p>
            Eva applique les cours ML dans sa boucle: cas proches, scores de routes,
            penalites, cross-validation et preuve locale avant reponse.
          </p>
          <Field label="Souvenirs ML" value={mlAdaptation.knowledge_memories || 0} />
          <Field label="Routes recompensees" value={mlAdaptation.rewarded_routes || 0} />
          <Field label="Routes penalisees" value={mlAdaptation.penalized_routes || 0} />
          <Field label="Cas resolver" value={mlAdaptation.problem_cases || 0} />
          {mlAdaptation.lessons?.length ? (
            <div className="panel-list compact">
              {mlAdaptation.lessons.slice(0, 5).map((lesson) => (
                <div key={lesson.course} className="panel-row">
                  <div>
                    <strong>{lesson.course}</strong>
                    <span>{lesson.adaptation}</span>
                  </div>
                  <StatusPill tone="ok">{lesson.status}</StatusPill>
                </div>
              ))}
            </div>
          ) : null}
        </section>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Memoire vectorielle locale</h3>
            <StatusPill tone={embeddings.enabled ? "ok" : "warning"}>
              {embeddings.enabled ? embeddings.model || "active" : "off"}
            </StatusPill>
          </div>
          <p>Eva utilise SQLite + FTS + embeddings Ollama locaux pour retrouver les souvenirs utiles avant de choisir une action.</p>
          <Field label="Ollama" value={embeddings.ollama_base_url || "local"} />
          <Field label="Candidats analyses" value={embeddings.candidate_limit || 0} />
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button"
              onClick={handleRebuildEmbeddings}
              disabled={Boolean(runningJob) || !embeddings.enabled}
            >
              {runningJob === "embeddings_rebuild" ? "Indexation..." : "Reconstruire les embeddings"}
            </button>
          </div>
        </section>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Vault Obsidian local</h3>
            <StatusPill tone={obsidian.exists ? "ok" : "warning"}>{obsidian.exists ? "pret" : "absent"}</StatusPill>
          </div>
          <p>{obsidian.path || "Vault local non configure."}</p>
          <Field label="Fichiers Markdown" value={obsidian.markdown_files || 0} />
          <Field label="Notes editables" value={obsidian.importable_notes || 0} />
          <Field label="Notes Eva" value={obsidian.managed_notes || 0} />
          <Field label="Cerveau Eva" value={obsidian.brain_hydrated ? "rempli" : "a remplir"} />
          <Field label="Organisation" value={obsidian.organized ? "propre" : "a ranger"} />
          <p>
            Ecris tes gouts, idees et regles dans Obsidian, puis importe-les: Eva les ajoute a SQLite,
            les retrouve en FTS/vectoriel et les reinjecte dans ses decisions.
          </p>
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button primary"
              onClick={handleOrganizeObsidian}
              disabled={Boolean(runningJob)}
            >
              {runningJob === "obsidian_organize" ? "Rangement..." : "Organiser le coffre"}
            </button>
            <button
              type="button"
              className="panel-action-button primary"
              onClick={handleHydrateObsidian}
              disabled={Boolean(runningJob)}
            >
              {runningJob === "obsidian_hydrate" ? "Remplissage..." : "Remplir le cerveau"}
            </button>
            <button
              type="button"
              className="panel-action-button primary"
              onClick={handleSeedObsidian}
              disabled={Boolean(runningJob)}
            >
              {runningJob === "obsidian_seed" ? "Nourrissage..." : "Nourrir la memoire"}
            </button>
            <button
              type="button"
              className="panel-action-button"
              onClick={handleOpenObsidian}
              disabled={Boolean(runningJob)}
            >
              {runningJob === "obsidian_open" ? "Ouverture..." : "Ouvrir le coffre"}
            </button>
            <button
              type="button"
              className="panel-action-button"
              onClick={handleImportObsidian}
              disabled={Boolean(runningJob) || !obsidian.exists}
            >
              {runningJob === "obsidian_import" ? "Import..." : "Importer notes Obsidian"}
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

  function renderRoles() {
    const roles = data?.roles || [];
    const selected = data?.selected || [];
    const lanes = new Set(roles.map((role) => role.lane));
    const orchestrator = data?.orchestrator || selected[0] || {};

    return (
      <>
        <div className="panel-metrics">
          <Metric label="roles" value={roles.length} tone={roles.length ? "ok" : "warning"} />
          <Metric label="lanes" value={lanes.size} />
          <Metric label="selection active" value={selected.length} tone={selected.length ? "ok" : "neutral"} />
        </div>
        <section className="panel-card role-orchestrator-card">
          <div className="panel-card-heading">
            <div>
              <span className="panel-section-kicker">Orchestrateur</span>
              <h3>{orchestrator.label || "Chief Executive Officer"}</h3>
            </div>
            <StatusPill tone="ok">{data?.active_model || "local_roles"}</StatusPill>
          </div>
          <p>{orchestrator.mission || "Eva choisit une posture avant de repondre ou d'agir."}</p>
          <div className="panel-chip-list">
            {selected.map((role) => (
              <StatusPill key={role.key} tone="ok">
                {role.label}
              </StatusPill>
            ))}
          </div>
        </section>
        <div className="panel-grid roles-grid">
          {roles.map((role) => (
            <section key={role.key} className={`panel-card role-card ${role.selected ? "selected" : ""}`}>
              <div className="panel-card-heading">
                <h3>{role.label}</h3>
                <StatusPill tone={role.selected ? "ok" : "neutral"}>{role.selected ? "active" : role.lane}</StatusPill>
              </div>
              <p>{role.mission}</p>
              <div className="skill-card-meta">
                <Field label="Lane" value={role.lane} />
                <Field label="Model hint" value={role.model_hint} />
                <Field label="Score" value={role.score || 0} />
              </div>
              <div className="panel-chip-list">
                {(role.triggers || []).slice(0, 6).map((trigger) => (
                  <StatusPill key={trigger}>{trigger}</StatusPill>
                ))}
              </div>
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

  function renderCuriosity() {
    const recent = data?.recent || [];
    const rules = Array.isArray(data?.rules) ? data.rules : [];
    const focus = Array.isArray(data?.focus) ? data.focus : [];
    const wikipediaTopics = Array.isArray(data?.wikipedia_topics) ? data.wikipedia_topics : [];
    const lastResult = data?.state?.last_result || {};
    const lastRunAt = data?.state?.last_run_at || "";

    return (
      <>
        <div className="panel-metrics">
          <Metric label="boucle" value={data?.enabled ? "active" : "manuelle"} tone={data?.enabled ? "ok" : "warning"} />
          <Metric label="lectures utiles" value={data?.total_items || 0} tone={data?.total_items ? "ok" : "neutral"} />
          <Metric label="cadence" value={`${data?.interval_minutes || 0} min`} />
          <Metric label="seuil" value={data?.min_score ?? 0} />
        </div>
        {jobResult && <div className="panel-success">{jobResult}</div>}
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Boucle de curiosite controlee</h3>
            <StatusPill tone={data?.enabled ? "ok" : "warning"}>
              {data?.enabled ? "h24" : "off par defaut"}
            </StatusPill>
          </div>
          <p>
            Eva peut lire des sources publiques en arriere-plan, filtrer ce qui sert tes projets,
            puis transformer chaque lecture en souvenir court dans SQLite et Obsidian.
          </p>
          <Field label="Dernier passage" value={lastRunAt ? new Date(lastRunAt).toLocaleString() : "jamais"} />
          <Field label="Candidats dernier passage" value={lastResult.candidates ?? 0} />
          <Field label="Self-study Wikipedia" value={lastResult.targeted_candidates ?? 0} />
          <Field label="RSS / veille" value={lastResult.rss_candidates ?? 0} />
          <Field label="Apprentissages dernier passage" value={lastResult.learned ?? 0} />
          <Field label="Rapport Obsidian" value={lastResult.report_path ? "cree" : "aucun"} />
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button primary"
              onClick={handleRunCuriosity}
              disabled={Boolean(runningJob)}
            >
              <BookOpen size={15} aria-hidden="true" />
              {runningJob === "curiosity_run" ? "Lecture..." : "Lire maintenant"}
            </button>
          </div>
        </section>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Curriculum self-study</h3>
            <StatusPill tone={wikipediaTopics.length ? "ok" : "neutral"}>{wikipediaTopics.length} sujets</StatusPill>
          </div>
          <div className="panel-list compact">
            {wikipediaTopics.slice(0, 8).map((topic) => (
              <div key={`${topic.language}-${topic.title}`} className="panel-row muted-row">
                <div>
                  <strong>{topic.title}</strong>
                  <span>{topic.reason}</span>
                </div>
                <StatusPill tone="ok">{topic.category}</StatusPill>
              </div>
            ))}
          </div>
        </section>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Focus Victor</h3>
            <StatusPill tone="ok">{focus.length} axes</StatusPill>
          </div>
          <div className="panel-chip-list">
            {focus.slice(0, 14).map((item) => (
              <StatusPill key={item} tone="ok">{item}</StatusPill>
            ))}
          </div>
          {rules.length ? (
            <div className="panel-list compact">
              {rules.slice(0, 5).map((rule) => (
                <div key={rule} className="panel-row muted-row">
                  <strong>{rule}</strong>
                </div>
              ))}
            </div>
          ) : null}
        </section>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Dernieres lectures retenues</h3>
            <StatusPill tone={recent.length ? "ok" : "neutral"}>{recent.length}</StatusPill>
          </div>
          {!recent.length ? (
            <div className="panel-empty">
              Rien appris pour l'instant. Lance une lecture manuelle ou active EVA_CURIOSITY_ENABLED=true.
            </div>
          ) : (
            <div className="panel-list">
              {recent.slice(0, 10).map((item) => (
                <div key={item.id || item.url} className="panel-row">
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.insight}</span>
                    <span className="panel-row-note">{item.source} - score {item.score} - memoire #{item.memory_id || "non stockee"}</span>
                  </div>
                  <div className="panel-row-actions">
                    <StatusPill tone={item.score >= 20 ? "ok" : "neutral"}>{item.category}</StatusPill>
                    {item.url ? (
                      <a className="panel-row-link" href={item.url} target="_blank" rel="noreferrer">
                        ouvrir
                      </a>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
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

  async function handleCreateAutonomyJob() {
    const instruction = autonomyJobInstruction.trim();
    if (!instruction) return;
    setRunningJob("autonomy_job_create");
    setJobResult("");
    setError("");
    try {
      const result = await createAutonomyJob(instruction);
      setAutonomyJobInstruction("");
      await loadPanel();
      setJobResult(`Job ajoute: ${result.job?.id || "queue locale"}. Eva le traitera en arriere-plan.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  async function handleRunNextAutonomyJob() {
    setRunningJob("autonomy_job_run_next");
    setJobResult("");
    setError("");
    try {
      const result = await runNextAutonomyJob();
      await loadPanel();
      setJobResult(result.ran ? `Job traite: ${result.job?.id || "termine"}.` : "Aucun job en attente.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunningJob("");
    }
  }

  function renderJobs() {
    const runner = data?.runner || data?.status || {};
    const counts = runner.counts || data?.status?.counts || {};
    const jobs = data?.jobs || [];
    const running = runner.running;

    return (
      <>
        <div className="panel-metrics">
          <Metric label="runner" value={runner.enabled ? "actif" : "off"} tone={runner.enabled ? "ok" : "warning"} />
          <Metric label="en attente" value={counts.queued || 0} tone={counts.queued ? "warning" : "neutral"} />
          <Metric label="en cours" value={counts.running || (running ? 1 : 0)} tone={running ? "ok" : "neutral"} />
          <Metric label="checkpoints" value={`/${runner.checkpoint_every || 12}`} />
        </div>
        {jobResult && <div className="panel-success">{jobResult}</div>}
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Queue autonome locale</h3>
            <StatusPill tone={runner.enabled ? "ok" : "warning"}>{runner.enabled ? "online" : "desactivee"}</StatusPill>
          </div>
          <p>Eva execute les jobs un par un, sauvegarde le resultat dans data/eva_jobs, ecrit des checkpoints JSONL et reprend un job interrompu au redemarrage.</p>
          <textarea
            className="panel-textarea"
            value={autonomyJobInstruction}
            onChange={(event) => setAutonomyJobInstruction(event.target.value)}
            placeholder="Ex: Continue le projet F1 en autonomie: ouvre le workspace, lance Cursor Agent, audite le resultat et relance une correction si besoin."
            rows={5}
          />
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button primary"
              onClick={handleCreateAutonomyJob}
              disabled={Boolean(runningJob) || !autonomyJobInstruction.trim()}
            >
              {runningJob === "autonomy_job_create" ? "Ajout..." : "Ajouter a la queue"}
            </button>
            <button
              type="button"
              className="panel-action-button"
              onClick={handleRunNextAutonomyJob}
              disabled={Boolean(runningJob)}
            >
              <Play size={15} aria-hidden="true" />
              {runningJob === "autonomy_job_run_next" ? "Execution..." : "Executer le prochain"}
            </button>
          </div>
        </section>
        {running && (
          <section className="panel-card job-running-card">
            <div className="panel-card-heading">
              <h3>En cours</h3>
              <StatusPill tone="ok">{running.id}</StatusPill>
            </div>
            <p>{running.instruction}</p>
            <Field label="Tentative" value={`${running.attempts || 0}/${running.max_attempts || 1}`} />
          </section>
        )}
        {jobs.length ? (
          <div className="panel-list">
            {jobs.map((job) => (
              <div key={job.id} className="panel-row">
                <div>
                  <strong>{job.instruction}</strong>
                  <span>{job.id} / {job.kind} / {job.source}</span>
                  {job.result_summary && <span className="panel-row-note">{job.result_summary}</span>}
                  {job.last_error && <span className="panel-row-note">{job.last_error}</span>}
                </div>
                <div className="panel-row-actions">
                  <StatusPill tone={statusClass(job.status)}>{job.status}</StatusPill>
                  <StatusPill>{`${job.attempts || 0}/${job.max_attempts || 1}`}</StatusPill>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState>Aucun job autonome. Ajoute une tache longue ou envoie /job depuis Telegram.</EmptyState>
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

  function renderResolver() {
    const recent = data?.recent || [];
    const byType = data?.by_type || {};
    const topType = Object.entries(byType)[0];

    return (
      <>
        <div className="panel-metrics">
          <Metric label="traces" value={data?.total || 0} tone={data?.total ? "warning" : "ok"} />
          <Metric label="dernier type" value={topType?.[0] || "clean"} tone={topType ? "warning" : "ok"} />
          <Metric label="mode" value={data?.enabled ? "actif" : "off"} tone={data?.enabled ? "ok" : "warning"} />
        </div>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Regle de conduite</h3>
            <StatusPill tone="ok">anti-refus passif</StatusPill>
          </div>
          <p>{data?.policy || "Eva journalise les blocages et cherche une route alternative sure."}</p>
          <div className="panel-actions">
            <button
              type="button"
              className="panel-action-button"
              onClick={() => onPrompt("Teste le resolver: ouvre une app locale, et si ca bloque trouve une autre route sure puis explique les pistes tentees.")}
            >
              Tester le resolver
            </button>
            <button
              type="button"
              className="panel-action-button secondary"
              onClick={() => onPrompt("Regarde les derniers blocages Eva et propose comment les rendre plus autonomes.")}
            >
              Analyser les blocages
            </button>
          </div>
        </section>
        {recent.length ? (
          <div className="panel-list">
            {recent.map((event) => (
              <div key={event.id} className="panel-row resolver-row">
                <div>
                  <strong>#{event.id} {event.problem_type} / {event.tool}</strong>
                  <span>{event.summary}</span>
                  {event.error && <span className="panel-row-note">{event.error}</span>}
                  {event.alternate_routes?.length ? (
                    <span className="panel-row-note">Plan B: {event.alternate_routes.join(" -> ")}</span>
                  ) : null}
                </div>
                <div className="panel-row-actions">
                  <StatusPill tone={statusClass(event.status)}>{event.status}</StatusPill>
                  <StatusPill>{event.domain}</StatusPill>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState>Aucun blocage journalise. Le resolver est pret.</EmptyState>
        )}
      </>
    );
  }

  function renderReinforcement() {
    const stats = data?.stats || [];
    const recentEvents = data?.recent_events || [];
    const states = data?.states || [];
    const best = stats
      .filter((item) => item.attempts >= (data?.min_attempts || 1))
      .sort((a, b) => (b.policy_score || 0) - (a.policy_score || 0))[0];

    return (
      <>
        <div className="panel-metrics">
          <Metric label="events" value={data?.events || 0} tone={data?.events ? "ok" : "neutral"} />
          <Metric label="reward moyen" value={data?.avg_reward ?? 0} tone={rewardTone(data?.avg_reward || 0)} />
          <Metric label="penalites" value={data?.negative || 0} tone={data?.negative ? "warning" : "ok"} />
        </div>
        <section className="panel-card">
          <div className="panel-card-heading">
            <h3>Politique locale</h3>
            <StatusPill tone={data?.enabled ? "ok" : "warning"}>{data?.enabled ? "active" : "off"}</StatusPill>
          </div>
          <p>
            Eva n'entraine pas Ollama. Elle apprend une couche de decision locale:
            etat de la demande, route choisie, resultat, puis bonus ou penalite.
          </p>
          <Field label="Seuil de bascule" value={data?.switch_threshold ?? 0} />
          <Field label="Essais minimum" value={data?.min_attempts ?? 0} />
          <Field label="Exploration" value={data?.exploration_bonus ?? 0} />
        </section>
        {best && (
          <section className="panel-card">
            <div className="panel-card-heading">
              <h3>Route favorite actuelle</h3>
              <StatusPill tone={rewardTone(best.avg_reward)}>{best.action_key}</StatusPill>
            </div>
            <Field label="Etat" value={best.state_key} />
            <Field label="Score politique" value={best.policy_score} />
            <Field label="Moyenne reward" value={best.avg_reward} />
            <Field label="Tentatives" value={best.attempts} />
          </section>
        )}
        {states.length ? (
          <section className="panel-card">
            <div className="panel-card-heading">
              <h3>Etats appris</h3>
              <StatusPill>{states.length}</StatusPill>
            </div>
            <div className="panel-chip-list">
              {states.slice(0, 10).map((state) => (
                <StatusPill key={state.state_key} tone="neutral">
                  {state.state_key} / {state.actions}
                </StatusPill>
              ))}
            </div>
          </section>
        ) : null}
        {stats.length ? (
          <div className="panel-list">
            {stats.slice(0, 12).map((item) => (
              <div key={`${item.state_key}-${item.action_key}`} className="panel-row">
                <div>
                  <strong>{item.action_key}</strong>
                  <span>{item.state_key}</span>
                  <span className="panel-row-note">
                    avg {item.avg_reward} / score {item.policy_score} / {item.attempts} essai(s)
                  </span>
                </div>
                <div className="panel-row-actions">
                  <StatusPill tone={rewardTone(item.last_reward)}>{item.last_reward}</StatusPill>
                  <StatusPill tone={item.penalty_count ? "warning" : "ok"}>{item.penalty_count} malus</StatusPill>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState>Aucun signal reward pour le moment. Eva apprendra au fil des chats web et Telegram.</EmptyState>
        )}
        {recentEvents.length ? (
          <section className="panel-card">
            <div className="panel-card-heading">
              <h3>Derniers signaux</h3>
              <StatusPill>{recentEvents.length}</StatusPill>
            </div>
            <div className="panel-list compact">
              {recentEvents.slice(0, 8).map((event) => (
                <div key={event.id} className="panel-row">
                  <div>
                    <strong>#{event.id} {event.action_key}</strong>
                    <span>{event.state_key} / {event.reason}</span>
                  </div>
                  <StatusPill tone={rewardTone(event.reward)}>{event.reward}</StatusPill>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </>
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
    const checks = diagnostic?.checks || [];
    const okCount = checks.filter((check) => statusClass(check.status) === "ok").length;
    const warningCount = checks.filter((check) => statusClass(check.status) === "warning").length;
    const errorCount = checks.filter((check) => statusClass(check.status) === "error").length;

    return (
      <>
        <div className="panel-metrics">
          <Metric label="statut" value={diagnostic?.status || "scan"} tone={statusClass(diagnostic?.status)} />
          <Metric label="checks ok" value={`${okCount}/${checks.length || 0}`} tone={errorCount ? "error" : warningCount ? "warning" : "ok"} />
          <Metric label="mode" value="local only" tone="ok" />
        </div>
        <section className="panel-card doctor-summary-card">
          <div>
            <span className="panel-section-kicker">Etat systeme</span>
            <h3>{diagnostic?.status === "ok" ? "Eva est operationnelle" : "Points a surveiller"}</h3>
          </div>
          <p>{diagnostic?.summary || "Diagnostic en cours."}</p>
          <div className="doctor-status-strip">
            <StatusPill tone="ok">{okCount} ok</StatusPill>
            <StatusPill tone={warningCount ? "warning" : "neutral"}>{warningCount} warning</StatusPill>
            <StatusPill tone={errorCount ? "error" : "neutral"}>{errorCount} error</StatusPill>
          </div>
        </section>
        {renderDoctorChecks(checks)}
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
    if (panel === "roles") return renderRoles();
    if (panel === "heartbeat") return renderHeartbeat();
    if (panel === "curiosity") return renderCuriosity();
    if (panel === "gmail") return renderGmail();
    if (panel === "linkedin") return renderLinkedIn();
    if (panel === "projects") return renderProjects();
    if (panel === "brief") return renderBrief();
    if (panel === "projectFactory") return renderProjectFactory();
    if (panel === "jobs") return renderJobs();
    if (panel === "actions") return renderActions();
    if (panel === "resolver") return renderResolver();
    if (panel === "reinforcement") return renderReinforcement();
    if (panel === "ollama") return renderOllama();
    return renderDoctor();
  }

  return (
    <div className={`panel-window panel-window-${panel}`}>
      <div className={`control-panel control-panel-${panel}`}>
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
