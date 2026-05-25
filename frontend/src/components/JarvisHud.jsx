import { Activity, BrainCircuit, Cpu, ShieldCheck } from "lucide-react";
import { useMemo } from "react";


function latestCognitiveTrace(messages = []) {
  return [...messages]
    .reverse()
    .map((message) => message.cognitiveTrace || message.cognitive_trace)
    .find(Boolean);
}


function statusTone(status) {
  if (status?.state === "ready") return "ready";
  if (status?.state === "offline") return "offline";
  return "checking";
}

const microNodes = [
  [9, 22],
  [17, 48],
  [24, 31],
  [31, 69],
  [39, 18],
  [44, 55],
  [52, 39],
  [58, 77],
  [63, 24],
  [69, 61],
  [74, 35],
  [81, 72],
  [86, 28],
  [91, 54],
  [34, 84],
  [13, 76],
  [48, 12],
  [77, 89],
];


export function JarvisHud({
  status,
  doctor,
  loading,
  currentMode,
  messages = [],
  variant = "chat",
}) {
  const trace = useMemo(() => latestCognitiveTrace(messages), [messages]);
  const tone = statusTone(status);
  const modeLabel = currentMode?.label || "Chat";
  const hasDecision = loading || Boolean(trace);
  const traceStatus = trace?.status || (loading ? "processing" : "");
  const traceConfidence = Number(trace?.confidence) || (loading ? 64 : 0);
  const compact = variant === "panel";

  return (
    <div className={`jarvis-hud ${compact ? "jarvis-hud-panel" : "jarvis-hud-chat"}`} aria-hidden="true">
      <div className="hud-grid-plane" />
      <div className="hud-sweep" />
      <div className="hud-noise" />

      <div className="hud-corner hud-corner-tl" />
      <div className="hud-corner hud-corner-tr" />
      <div className="hud-corner hud-corner-bl" />
      <div className="hud-corner hud-corner-br" />

      {!compact && (
        <div className="hud-vitals hud-vitals-left">
          <div className="hud-readout">
            <Activity size={15} />
            <span>Core</span>
            <strong>{tone === "ready" ? "online" : tone}</strong>
            <i className={`hud-led ${tone}`} />
          </div>
          <div className="hud-readout">
            <BrainCircuit size={15} />
            <span>Mode</span>
            <strong>{modeLabel}</strong>
          </div>
          <div className="hud-readout">
            <Cpu size={15} />
            <span>Model</span>
            <strong>{status?.model || "Ollama"}</strong>
          </div>
        </div>
      )}

      {!compact && (
        <div className={`hud-radar ${loading ? "active" : ""}`}>
          <span className="hud-radar-ring ring-a" />
          <span className="hud-radar-ring ring-b" />
          <span className="hud-radar-ring ring-c" />
          <span className="hud-radar-sweep" />
          <strong>Eva</strong>
        </div>
      )}

      {!compact && hasDecision && (
        <div className="hud-decision-strip">
          <span>Decision stream</span>
          <strong>{trace?.selected || "Analyse en cours"}</strong>
          <em>{traceStatus}</em>
          <i style={{ "--hud-confidence": `${Math.min(100, Math.max(0, traceConfidence))}%` }} />
        </div>
      )}

      {!compact && doctor?.status && doctor.status !== "ok" && (
        <div className="hud-doctor-alert">
          <ShieldCheck size={14} />
          <span>Doctor</span>
          <strong>{doctor.status}</strong>
        </div>
      )}

      <div className="hud-micro-nodes">
        {microNodes.map(([x, y], index) => (
          <span
            key={`${x}-${y}`}
            style={{ "--node-index": index, "--node-x": `${x}%`, "--node-y": `${y}%` }}
          />
        ))}
      </div>
    </div>
  );
}
