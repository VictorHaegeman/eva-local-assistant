export function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const briefItems = Array.isArray(message.briefItems) ? message.briefItems : [];
  const suggestedTabs = Array.isArray(message.suggestedTabs) ? message.suggestedTabs : [];
  const webPreview = message.webPreview || message.web_preview || null;
  const isMapPreview = webPreview?.type === "map" && webPreview?.embed_url;
  const isExternalPreview = webPreview && !isMapPreview && webPreview.url;

  return (
    <article className={`message-row ${message.role}`}>
      {!isUser && <div className="avatar">E</div>}
      <div className="message-stack">
        <span className="message-author">{isUser ? "Victor" : "Eva"}</span>
        <div className="message-bubble">
          {message.content}

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
            <div className="web-preview-card map-preview-card">
              <div className="web-preview-head">
                <span>{webPreview.provider || "Carte"}</span>
                <strong>{webPreview.title || webPreview.label || "Carte interactive"}</strong>
              </div>
              <iframe
                title={webPreview.title || "Carte interactive"}
                src={webPreview.embed_url}
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
              <div className="web-preview-actions">
                <button
                  type="button"
                  onClick={() => window.open(webPreview.url, "_blank", "noopener,noreferrer")}
                >
                  Ouvrir dans Brave
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
