export function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const briefItems = Array.isArray(message.briefItems) ? message.briefItems : [];
  const suggestedTabs = Array.isArray(message.suggestedTabs) ? message.suggestedTabs : [];

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
        </div>
      </div>
      {isUser && <div className="avatar user-avatar">V</div>}
    </article>
  );
}
