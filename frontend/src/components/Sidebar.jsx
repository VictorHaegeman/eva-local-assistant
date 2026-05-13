import { Cpu, LockKeyhole, MessageSquarePlus, RotateCcw, Sparkles, Wifi } from "lucide-react";


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
        Nouveau canal
      </button>

      <div className="sidebar-section">
        <p className="section-label">Systemes locaux</p>
        <div className="capability">
          <Cpu size={18} aria-hidden="true" />
          <span>IA via Ollama</span>
        </div>
        <div className="capability">
          <Wifi size={18} aria-hidden="true" />
          <span>Acces reseau Wi-Fi</span>
        </div>
        <div className="capability">
          <LockKeyhole size={18} aria-hidden="true" />
          <span>Actions avec validation</span>
        </div>
      </div>

      <div className="sidebar-footer">
        <RotateCcw size={16} aria-hidden="true" />
        <span>Mode local. Validation humaine active.</span>
      </div>
    </aside>
  );
}
