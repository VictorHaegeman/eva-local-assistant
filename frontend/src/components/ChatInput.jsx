import { useState } from "react";
import { Mic, SendHorizontal } from "lucide-react";


export function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState("");
  const [listening, setListening] = useState(false);

  const SpeechRecognition =
    typeof window !== "undefined" &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);

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

  function startVoiceInput() {
    if (!SpeechRecognition || disabled || listening) return;

    const recognition = new SpeechRecognition();
    recognition.lang = "fr-FR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setListening(true);
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim();
      if (!transcript) return;
      setValue(transcript);
      onSend(transcript);
      setValue("");
    };

    recognition.start();
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
          className={`voice-button ${listening ? "listening" : ""}`}
          onClick={startVoiceInput}
          disabled={disabled || !SpeechRecognition}
          title="Parler a Eva"
          aria-label="Parler a Eva"
        >
          <Mic size={18} aria-hidden="true" />
        </button>
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
