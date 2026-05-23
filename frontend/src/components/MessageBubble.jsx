import {
  Crosshair,
  ExternalLink,
  MapPinned,
  Maximize2,
  Minimize2,
  Navigation,
  Play,
  Route,
  Satellite,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";


function buildMapLinks(webPreview) {
  const label = encodeURIComponent(webPreview?.label || "carte");
  const hasCoords = Number.isFinite(Number(webPreview?.lat)) && Number.isFinite(Number(webPreview?.lon));
  const coords = hasCoords ? `${webPreview.lat},${webPreview.lon}` : label;

  return {
    osm: webPreview?.url || `https://www.openstreetmap.org/search?query=${label}`,
    googleMaps:
      webPreview?.google_maps_url ||
      `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(coords)}`,
    directions:
      webPreview?.directions_url ||
      `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(coords)}`,
    googleEarth:
      webPreview?.google_earth_url ||
      `https://earth.google.com/web/search/${label}`,
  };
}


function CognitiveTrace({ trace }) {
  const stages = Array.isArray(trace?.stages) ? trace.stages : [];
  const routeStage = stages.find((stage) => Array.isArray(stage.options));
  const routeOptions = routeStage?.options || [];
  const evidence = Array.isArray(trace?.evidence) ? trace.evidence : [];
  const [reveal, setReveal] = useState(1);
  const maxReveal = stages.length + (routeOptions.length ? 1 : 0) + (evidence.length ? 1 : 0);

  useEffect(() => {
    setReveal(1);
    const timer = window.setInterval(() => {
      setReveal((current) => {
        if (current >= maxReveal) {
          window.clearInterval(timer);
          return current;
        }
        return current + 1;
      });
    }, 420);

    return () => window.clearInterval(timer);
  }, [maxReveal]);

  if (!stages.length) return null;

  return (
    <section className="cognitive-trace" aria-label="Decision Eva">
      <div className="trace-network" aria-hidden="true">
        <span className="node node-a" />
        <span className="node node-b" />
        <span className="node node-c" />
      </div>
      <div className="trace-header">
        <span>Eva Pipeline</span>
        <strong>{trace.selected || "Route selectionnee"}</strong>
        <em>{trace.confidence || 0}%</em>
      </div>
      <p>{trace.summary}</p>

      <div className="trace-stage-grid">
        {stages.map((stage, index) => (
          <div
            className={`trace-stage ${stage.status || "pending"} ${index < reveal ? "visible" : "pending-visual"}`}
            key={stage.key || stage.label}
          >
            <span>Stage {String(index + 1).padStart(2, "0")}</span>
            <strong>{stage.label}</strong>
            <small>{stage.detail}</small>
          </div>
        ))}
      </div>

      {routeOptions.length > 0 && reveal > stages.length && (
        <div className="trace-routes">
          {routeOptions.map((option) => (
            <div className={`trace-route ${option.selected ? "selected" : ""}`} key={option.key || option.label}>
              <span>{option.label}</span>
              <strong>{option.score}%</strong>
            </div>
          ))}
        </div>
      )}

      {evidence.length > 0 && reveal > stages.length + (routeOptions.length ? 1 : 0) && (
        <div className="trace-evidence">
          {evidence.slice(0, 3).map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      )}
    </section>
  );
}

export function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const briefItems = Array.isArray(message.briefItems) ? message.briefItems : [];
  const suggestedTabs = Array.isArray(message.suggestedTabs) ? message.suggestedTabs : [];
  const webPreview = message.webPreview || message.web_preview || null;
  const cognitiveTrace = message.cognitiveTrace || message.cognitive_trace || null;
  const isMapPreview = webPreview?.type === "map" && webPreview?.embed_url;
  const isExternalPreview = webPreview && !isMapPreview && webPreview.url;
  const mapLinks = useMemo(() => buildMapLinks(webPreview), [webPreview]);
  const [mapExpanded, setMapExpanded] = useState(false);
  const latitude = Number(webPreview?.lat);
  const longitude = Number(webPreview?.lon);
  const hasMapCoords = Number.isFinite(latitude) && Number.isFinite(longitude);

  return (
    <article className={`message-row ${message.role}`}>
      {!isUser && <div className="avatar">E</div>}
      <div className="message-stack">
        <span className="message-author">{isUser ? "Victor" : "Eva"}</span>
        <div className="message-bubble">
          {message.content}

          {!isUser && cognitiveTrace && <CognitiveTrace trace={cognitiveTrace} />}

          {briefItems.length > 0 && (
            <div className="brief-source-grid">
              {briefItems.map((item) => (
                <a
                  className="brief-source-card"
                  href={item.link || "#"}
                  target="_blank"
                  rel="noreferrer"
                  key={`${item.source}-${item.title}`}
                >
                  {item.image ? (
                    <img src={item.image} alt="" loading="lazy" />
                  ) : (
                    <span className="brief-source-image-fallback">{item.category || "news"}</span>
                  )}
                  <span className="brief-source-meta">
                    {item.source} · {item.category}
                  </span>
                  <strong>{item.title}</strong>
                </a>
              ))}
            </div>
          )}

          {suggestedTabs.length > 0 && (
            <div className="brief-tabs">
              <span>Onglets importants</span>
              {suggestedTabs.map((tab) => (
                <button
                  type="button"
                  key={tab.url}
                  onClick={() => window.open(tab.url, "_blank", "noopener,noreferrer")}
                >
                  {tab.title || tab.source || "Ouvrir"}
                </button>
              ))}
            </div>
          )}

          {isMapPreview && (
            <div className={`web-preview-card map-preview-card ${mapExpanded ? "expanded" : ""}`}>
              <div className="jarvis-map-topbar">
                <div>
                  <span>Eva tactical map</span>
                  <strong>{webPreview.label || webPreview.title || "Carte interactive"}</strong>
                </div>
                <div className="jarvis-map-chips">
                  <span>{webPreview.provider || "Carte"}</span>
                  {hasMapCoords && <span>{latitude.toFixed(4)}, {longitude.toFixed(4)}</span>}
                </div>
              </div>
              <div className="web-preview-actions map-primary-actions">
                <button
                  className="primary"
                  type="button"
                  onClick={() => window.open(mapLinks.googleMaps, "_blank", "noopener,noreferrer")}
                >
                  <Navigation size={16} aria-hidden="true" />
                  Ouvrir Google Maps
                </button>
                <button
                  type="button"
                  onClick={() => window.open(mapLinks.directions, "_blank", "noopener,noreferrer")}
                >
                  <Route size={16} aria-hidden="true" />
                  Itineraire
                </button>
                <button
                  type="button"
                  onClick={() => setMapExpanded((current) => !current)}
                >
                  {mapExpanded ? <Minimize2 size={16} aria-hidden="true" /> : <Maximize2 size={16} aria-hidden="true" />}
                  {mapExpanded ? "Reduire" : "Agrandir"}
                </button>
              </div>
              <div className="jarvis-map-display">
                <iframe
                  title={webPreview.title || "Carte interactive"}
                  src={webPreview.embed_url}
                  loading="lazy"
                  referrerPolicy="no-referrer-when-downgrade"
                  allowFullScreen
                />
                <div className="jarvis-map-corner top-left" aria-hidden="true" />
                <div className="jarvis-map-corner top-right" aria-hidden="true" />
                <div className="jarvis-map-corner bottom-left" aria-hidden="true" />
                <div className="jarvis-map-corner bottom-right" aria-hidden="true" />
                <div className="jarvis-map-readout left">
                  <span>Target</span>
                  <strong>{webPreview.label || "Position"}</strong>
                  <small>{hasMapCoords ? `${latitude.toFixed(5)} / ${longitude.toFixed(5)}` : "Coordonnees indisponibles"}</small>
                </div>
                <button
                  className="jarvis-map-play"
                  type="button"
                  onClick={() => window.open(mapLinks.googleMaps, "_blank", "noopener,noreferrer")}
                  aria-label="Ouvrir la carte dans Google Maps"
                >
                  <Play size={34} aria-hidden="true" />
                </button>
                <div className="jarvis-map-radar" aria-hidden="true">
                  <span />
                  <strong>EVA</strong>
                </div>
                <div className="jarvis-map-status">
                  <span>
                    <Crosshair size={13} aria-hidden="true" />
                    Lock
                  </span>
                  <span>Zoom online</span>
                  <span>Map layer active</span>
                </div>
              </div>
              <div className="web-preview-actions">
                <button
                  type="button"
                  onClick={() => window.open(mapLinks.osm, "_blank", "noopener,noreferrer")}
                >
                  <ExternalLink size={16} aria-hidden="true" />
                  OSM complet
                </button>
                <button
                  type="button"
                  onClick={() => window.open(mapLinks.googleMaps, "_blank", "noopener,noreferrer")}
                >
                  <Navigation size={16} aria-hidden="true" />
                  Google Maps
                </button>
                <button
                  type="button"
                  onClick={() => window.open(mapLinks.googleEarth, "_blank", "noopener,noreferrer")}
                >
                  <Satellite size={16} aria-hidden="true" />
                  Vue 3D
                </button>
              </div>
            </div>
          )}

          {isExternalPreview && (
            <div className="web-preview-card external-preview-card">
              <div className="web-preview-head">
                <span>{webPreview.provider || "Lien"}</span>
                <strong>{webPreview.title || webPreview.label || "Apercu externe"}</strong>
              </div>
              <div className="external-preview-body">
                <span>{webPreview.label || webPreview.url}</span>
              </div>
              <div className="web-preview-actions">
                <button
                  type="button"
                  onClick={() => window.open(webPreview.url, "_blank", "noopener,noreferrer")}
                >
                  <ExternalLink size={16} aria-hidden="true" />
                  Ouvrir dans Brave
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
      {isUser && <div className="avatar user-avatar">V</div>}
    </article>
  );
}
