import {
  Bot,
  BrainCircuit,
  CheckCircle2,
  Cpu,
  Eye,
  GitBranch,
  HeartPulse,
  Layers3,
  Mail,
  MessagesSquare,
  MessageSquarePlus,
  Network,
  Newspaper,
  Rocket,
  Route,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Terminal,
  TriangleAlert,
  Wifi,
  Wrench,
} from "lucide-react";


function getStatusLabel(status) {
  if (status.state === "ready") return "Connectee";
  if (status.state === "offline") return "Backend indisponible";
  return "Verification";
}


function getDoctorLabel(doctor) {
  if (doctor.status === "ok") return "OK";
  if (doctor.status === "warning") return "Attention";
  if (doctor.status === "error") return "Erreur";
  return "Scan";
}


function getDoctorIcon(doctor) {
  if (doctor.status === "ok") return <CheckCircle2 size={16} aria-hidden="true" />;
  if (doctor.status === "error") return <TriangleAlert size={16} aria-hidden="true" />;
  return <Stethoscope size={16} aria-hidden="true" />;
}


const coreItems = [
  {
    icon: Bot,
    label: "Chat local",
    panel: "chat",
  },
  {
    icon: MessagesSquare,
    label: "Chats",
    panel: "chats",
  },
  {
    icon: BrainCircuit,
    label: "Memoire",
    panel: "memory",
  },
  {
    icon: Eye,
    label: "Ecran",
    panel: "screen",
  },
  {
    icon: Wrench,
    label: "Tools",
    panel: "tools",
  },
  {
    icon: Layers3,
    label: "Skills",
    panel: "skills",
  },
  {
    icon: HeartPulse,
    label: "Heartbeat",
    panel: "heartbeat",
  },
  {
    icon: Mail,
    label: "Gmail",
    panel: "gmail",
  },
  {
    icon: Network,
    label: "LinkedIn",
    panel: "linkedin",
  },
  {
    icon: GitBranch,
    label: "Projets",
    panel: "projects",
  },
];


const operationItems = [
  {
    icon: Newspaper,
    label: "Brief",
    panel: "brief",
  },
  {
    icon: Rocket,
    label: "Factory",
    panel: "projectFactory",
  },
  {
    icon: Terminal,
    label: "Actions",
    panel: "actions",
  },
  {
    icon: Route,
    label: "Resolver",
    panel: "resolver",
  },
  {
    icon: Cpu,
    label: "Ollama",
    panel: "ollama",
  },
];


export function Sidebar({
  status,
  doctor,
  modes,
  activeMode,
  activePanel,
  onModeChange,
  onPanelChange = () => {},
  onReset,
}) {
  const visibleChecks = doctor.checks?.slice(0, 3) || [];
  const safeModes = modes.length ? modes : [{ name: "chat", label: "Chat", description: "Mode general" }];

  function handleNewChat() {
    onReset();
    onPanelChange("chat");
  }

  return (
    <aside className="sidebar" aria-label="Eva">
      <div className="sidebar-brand">
        <div className="brand-mark">
          <Sparkles size={24} aria-hidden="true" />
        </div>
        <div>
          <h1>Eva</h1>
          <p>Assistante locale de Victor</p>
        </div>
      </div>

      <div className="status-panel">
        <div className="status-line">
          <span className={`status-dot ${status.state}`} />
          <span>{getStatusLabel(status)}</span>
        </div>
        <p>{status.model ? `Modele: ${status.model}` : "Ollama local"}</p>
      </div>

      <button type="button" className="new-chat-button" onClick={handleNewChat}>
        <MessageSquarePlus size={18} aria-hidden="true" />
        Nouveau chat
      </button>

      <div className="sidebar-section">
        <p className="section-label">Modes</p>
        <div className="mode-grid">
          {safeModes.map((mode) => (
            <button
              key={mode.name}
              type="button"
              className={`mode-button ${activeMode === mode.name ? "active" : ""}`}
              onClick={() => onModeChange(mode.name)}
              title={mode.description}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>

      <div className="sidebar-section">
        <p className="section-label">Core</p>
        {coreItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.label}
              type="button"
              className={`nav-item ${activePanel === item.panel ? "active" : ""}`}
              onClick={() => onPanelChange(item.panel)}
            >
              <Icon size={17} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      <div className="sidebar-section">
        <p className="section-label">Operations</p>
        {operationItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.label}
              type="button"
              className={`nav-item ${activePanel === item.panel ? "active" : ""}`}
              onClick={() => onPanelChange(item.panel)}
            >
              <Icon size={17} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className={`doctor-panel ${doctor.status} ${activePanel === "doctor" ? "active" : ""}`}
        onClick={() => onPanelChange("doctor")}
      >
        <div className="doctor-heading">
          {getDoctorIcon(doctor)}
          <span>Doctor</span>
          <strong>{getDoctorLabel(doctor)}</strong>
        </div>
        <p>{doctor.summary}</p>
        {visibleChecks.length > 0 && (
          <div className="doctor-checks">
            {visibleChecks.map((check) => (
              <div key={check.name} className={`doctor-check ${check.status}`}>
                <span />
                <small>{check.message}</small>
              </div>
            ))}
          </div>
        )}
      </button>

      <div className="sidebar-footer">
        <div>
          <ShieldCheck size={16} aria-hidden="true" />
          <span>Local uniquement</span>
        </div>
        <div>
          <Wifi size={16} aria-hidden="true" />
          <span>Wi-Fi personnel</span>
        </div>
        <div>
          <RotateCcw size={16} aria-hidden="true" />
          <span>Validation humaine</span>
        </div>
      </div>
    </aside>
  );
}
