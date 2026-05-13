import { useState } from "react";
import { SendHorizontal } from "lucide-react";


export function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState("");

  function submit() {
    const cleanValue = value.trim();
    if (!cleanValue || disabled) return;

    onSend(cleanValue);
    setValue("");
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <footer className="composer-shell">
      <div className="composer">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Transmettre a Eva..."
          rows={1}
          disabled={disabled}
          aria-label="Message pour Eva"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !value.trim()}
          title="Envoyer"
          aria-label="Envoyer le message"
        >
          <SendHorizontal size={20} aria-hidden="true" />
        </button>
      </div>
    </footer>
  );
}
