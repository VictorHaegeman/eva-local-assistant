import { useEffect, useRef } from "react";

import { EvaOrb } from "./EvaOrb";
import { MessageBubble } from "./MessageBubble";


const starters = [
  "Prepare mon brief DreamLense.",
  "Resume le fichier README.md.",
  "Cree un prompt Cursor pour ameliorer Eva.",
];


export function ChatWindow({ messages, loading, error, onStarterSelect, status }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading, error]);

  return (
    <div className="chat-window">
      <div className="messages">
        {messages.length === 1 && !loading && (
          <EvaOrb status={status} />
        )}

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {messages.length === 1 && !loading && (
          <div className="starter-row" aria-label="Suggestions de depart">
            {starters.map((starter) => (
              <button
                key={starter}
                type="button"
                onClick={() => onStarterSelect(starter)}
              >
                {starter}
              </button>
            ))}
          </div>
        )}

        {loading && (
          <div className="message-row assistant">
            <div className="avatar">E</div>
            <div className="typing-bubble" aria-label="Eva ecrit">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}

        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
}
