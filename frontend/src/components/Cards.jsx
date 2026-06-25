import { Calendar, CheckCircle, Circle, Clock, Mail, MapPin } from "lucide-react";
import { useState } from "react";

const CARD_ICONS = {
  task: CheckCircle,
  calendar: Calendar,
  mail: Mail,
  rdv_slot: Clock,
  priority: MapPin,
};

const CARD_COLORS = {
  blue: { border: "rgba(115,214,255,0.3)", glow: "rgba(115,214,255,0.08)", accent: "#73d6ff" },
  green: { border: "rgba(52,211,153,0.3)", glow: "rgba(52,211,153,0.08)", accent: "#34d399" },
  amber: { border: "rgba(251,191,36,0.3)", glow: "rgba(251,191,36,0.08)", accent: "#fbbf24" },
  purple: { border: "rgba(167,139,250,0.3)", glow: "rgba(167,139,250,0.08)", accent: "#a78bfa" },
  red: { border: "rgba(248,113,113,0.3)", glow: "rgba(248,113,113,0.08)", accent: "#f87171" },
};

function TaskCard({ card }) {
  const [done, setDone] = useState({});
  const color = CARD_COLORS[card.color] || CARD_COLORS.blue;

  return (
    <div className="eva-card" style={{ "--card-border": color.border, "--card-glow": color.glow, "--card-accent": color.accent }}>
      <div className="eva-card-header">
        <CheckCircle size={14} />
        <span>{card.title}</span>
      </div>
      <ul className="eva-card-tasks">
        {card.items.map((item) => (
          <li
            key={item.id}
            className={`eva-card-task-item ${done[item.id] ? "done" : ""} ${item.status === "urgent" ? "urgent" : ""}`}
            onClick={() => setDone((d) => ({ ...d, [item.id]: !d[item.id] }))}
          >
            {done[item.id] ? <CheckCircle size={13} /> : <Circle size={13} />}
            <span>{item.text}</span>
          </li>
        ))}
      </ul>
      {card.actions?.length > 0 && (
        <div className="eva-card-actions">
          {card.actions.map((a) => (
            <button key={a.action_key} className="eva-card-btn" type="button">
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function RdvSlotCard({ card }) {
  const [selected, setSelected] = useState(null);
  const color = CARD_COLORS[card.color] || CARD_COLORS.purple;

  return (
    <div className="eva-card" style={{ "--card-border": color.border, "--card-glow": color.glow, "--card-accent": color.accent }}>
      <div className="eva-card-header">
        <Clock size={14} />
        <span>{card.title}</span>
      </div>
      {card.subtitle && <p className="eva-card-subtitle">{card.subtitle}</p>}
      <div className="eva-card-slots">
        {card.items.map((slot) => (
          <button
            key={slot.id}
            type="button"
            className={`eva-card-slot-btn ${selected === slot.id ? "selected" : ""}`}
            onClick={() => setSelected(slot.id)}
          >
            {slot.text}
          </button>
        ))}
      </div>
      {card.actions?.length > 0 && (
        <div className="eva-card-actions">
          {card.actions.map((a) => (
            <button key={a.action_key} className="eva-card-btn secondary" type="button">
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CalendarCard({ card }) {
  const color = CARD_COLORS[card.color] || CARD_COLORS.green;

  return (
    <div className="eva-card" style={{ "--card-border": color.border, "--card-glow": color.glow, "--card-accent": color.accent }}>
      <div className="eva-card-header">
        <Calendar size={14} />
        <span>{card.title}</span>
      </div>
      <ul className="eva-card-events">
        {card.items.map((item) => (
          <li key={item.id} className="eva-card-event-item">
            <span className="eva-card-event-dot" />
            <span>{item.text}</span>
          </li>
        ))}
      </ul>
      {card.actions?.length > 0 && (
        <div className="eva-card-actions">
          {card.actions.map((a) => (
            <button key={a.action_key} className="eva-card-btn" type="button">
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function MailCard({ card }) {
  const color = CARD_COLORS[card.color] || CARD_COLORS.amber;

  return (
    <div className="eva-card" style={{ "--card-border": color.border, "--card-glow": color.glow, "--card-accent": color.accent }}>
      <div className="eva-card-header">
        <Mail size={14} />
        <span>{card.title}</span>
      </div>
      <ul className="eva-card-tasks">
        {card.items.map((item) => (
          <li key={item.id} className={`eva-card-task-item ${item.status === "urgent" ? "urgent" : ""}`}>
            <span className="eva-card-mail-dot" />
            <span>{item.text}</span>
          </li>
        ))}
      </ul>
      {card.actions?.length > 0 && (
        <div className="eva-card-actions">
          {card.actions.map((a) => (
            <button key={a.action_key} className="eva-card-btn" type="button">
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const CARD_RENDERERS = {
  task: TaskCard,
  rdv_slot: RdvSlotCard,
  calendar: CalendarCard,
  mail: MailCard,
};

export function CardList({ cards }) {
  if (!cards?.length) return null;

  return (
    <div className="eva-cards-list">
      {cards.map((card) => {
        const Renderer = CARD_RENDERERS[card.type];
        if (!Renderer) return null;
        return <Renderer key={card.id} card={card} />;
      })}
    </div>
  );
}
