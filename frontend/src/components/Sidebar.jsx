import {
  Bot,
  BrainCircuit,
  Cpu,
  Files,
  GitBranch,
  MessageSquarePlus,
  Newspaper,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Terminal,
  Wifi,
} from "lucide-react";


function getStatusLabel(status) {
  if (status.state === "ready") return "Connectee";
  if (status.state === "offline") return "Backend indisponible";
  return "Verification";
}


export function Sidebar({ status, onReset }) {
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

      <button type="button" className="new-chat-button" onClick={onReset}>
        <MessageSquarePlus size={18} aria-hidden="true" />
        Nouveau chat
      </button>

      <div className="sidebar-section">
        <p className="section-label">Workspace</p>
        <div className="nav-item active">
          <Bot size={17} aria-hidden="true" />
          <span>Chat local</span>
        </div>
        <div className="nav-item">
          <BrainCircuit size={17} aria-hidden="true" />
          <span>Memoire</span>
        </div>
        <div className="nav-item">
          <Files size={17} aria-hidden="true" />
          <span>Fichiers</span>
        </div>
        <div className="nav-item">
          <GitBranch size={17} aria-hidden="true" />
          <span>Projets</span>
        </div>
      </div>

      <div className="sidebar-section">
        <p className="section-label">Operations</p>
        <div className="nav-item">
          <Newspaper size={17} aria-hidden="true" />
          <span>Brief</span>
        </div>
        <div className="nav-item">
          <Terminal size={17} aria-hidden="true" />
          <span>Actions</span>
        </div>
        <div className="nav-item">
          <Cpu size={17} aria-hidden="true" />
          <span>Ollama</span>
        </div>
      </div>

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
