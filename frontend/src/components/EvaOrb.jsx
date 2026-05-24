export function EvaOrb({ status }) {
  const isReady = status?.state === "ready";
  const stateLabel = isReady ? "Core local actif" : "Connexion au core";

  return (
    <section className="eva-orb-stage" aria-label="Presentation Eva">
      <div className="eva-orb" aria-hidden="true">
        <div className="eva-orb-ring ring-one" />
        <div className="eva-orb-ring ring-two" />
        <div className="eva-orb-ring ring-three" />
        <div className="eva-orb-ring ring-four" />
        <div className="eva-orb-grid" />
        <div className="eva-orb-particles">
          {Array.from({ length: 16 }, (_, index) => (
            <span key={index} style={{ "--particle-index": index }} />
          ))}
        </div>
        <div className="eva-orb-axis axis-x" />
        <div className="eva-orb-axis axis-y" />
        <div className="eva-orb-core">
          <span>Eva</span>
        </div>
        <div className="eva-orb-status">
          <span>{isReady ? "ONLINE" : "SYNC"}</span>
          <strong>{status?.model || "local"}</strong>
        </div>
      </div>

      <div className="eva-orb-copy">
        <span className="eyebrow">Assistant local</span>
        <h1>Eva</h1>
        <p>{stateLabel}</p>
      </div>
    </section>
  );
}
