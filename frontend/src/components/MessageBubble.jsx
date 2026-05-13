export function MessageBubble({ message }) {
  const isUser = message.role === "user";

  return (
    <article className={`message-row ${message.role}`}>
      {!isUser && <div className="avatar">E</div>}
      <div className="message-stack">
        <span className="message-author">{isUser ? "Victor" : "Eva"}</span>
        <div className="message-bubble">
          {message.content}
        </div>
      </div>
      {isUser && <div className="avatar user-avatar">V</div>}
    </article>
  );
}
