import { useEffect, useRef, useState } from "react";
import { Mic, Radio, SendHorizontal, Volume2, VolumeX } from "lucide-react";


function normalizeVoiceText(value) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}


function extractWakeCommand(transcript) {
  const match = transcript.match(/\b(?:ok\s+eva|eva)\b[\s,;:.-]*(.*)$/i);
  return match ? match[1].trim() : null;
}


export function ChatInput({ onSend, disabled, voiceReplies, onVoiceRepliesChange }) {
  const [value, setValue] = useState("");
  const [listening, setListening] = useState(false);
  const [wakeMode, setWakeMode] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("");
  const recognitionRef = useRef(null);
  const restartTimerRef = useRef(null);
  const wakeModeRef = useRef(false);
  const disabledRef = useRef(disabled);
  const armedUntilRef = useRef(0);

  const SpeechRecognition =
    typeof window !== "undefined" &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);

  useEffect(() => {
    disabledRef.current = disabled;
  }, [disabled]);

  useEffect(() => {
    wakeModeRef.current = wakeMode;
  }, [wakeMode]);

  useEffect(() => {
    return () => {
      window.clearTimeout(restartTimerRef.current);
      recognitionRef.current?.stop();
    };
  }, []);

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

  function sendVoiceCommand(command) {
    const cleanCommand = command.trim();
    if (!cleanCommand || disabledRef.current) return;

    setValue("");
    setVoiceStatus("Commande transmise");
    onSend(cleanCommand);
  }

  function handleWakeTranscript(transcript) {
    const cleanTranscript = transcript.trim();
    if (!cleanTranscript) return;

    const normalized = normalizeVoiceText(cleanTranscript);
    if (normalized === "stop" || normalized === "tais toi" || normalized === "tais-toi") {
      window.speechSynthesis?.cancel();
      setVoiceStatus("Voix stoppee");
      return;
    }

    const wakeCommand = extractWakeCommand(cleanTranscript);
    if (wakeCommand !== null) {
      if (wakeCommand) {
        sendVoiceCommand(wakeCommand);
      } else {
        armedUntilRef.current = Date.now() + 8000;
        setVoiceStatus("Eva ecoute");
      }
      return;
    }

    if (Date.now() < armedUntilRef.current) {
      armedUntilRef.current = 0;
      sendVoiceCommand(cleanTranscript);
    }
  }

  function startWakeRecognition() {
    if (!SpeechRecognition || disabledRef.current || !wakeModeRef.current) return;

    window.clearTimeout(restartTimerRef.current);
    recognitionRef.current?.stop();

    const recognition = new SpeechRecognition();
    recognition.lang = "fr-FR";
    recognition.interimResults = false;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setListening(true);
      setVoiceStatus("Dis Eva ou Ok Eva");
    };

    recognition.onerror = () => {
      setListening(false);
    };

    recognition.onend = () => {
      setListening(false);
      if (wakeModeRef.current && !disabledRef.current) {
        restartTimerRef.current = window.setTimeout(startWakeRecognition, 500);
      }
    };

    recognition.onresult = (event) => {
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        if (!event.results[index].isFinal) continue;
        const transcript = event.results[index][0]?.transcript || "";
        handleWakeTranscript(transcript);
      }
    };

    recognitionRef.current = recognition;
    recognition.start();
  }

  function toggleWakeMode() {
    if (!SpeechRecognition || disabled) return;

    if (wakeMode) {
      wakeModeRef.current = false;
      setWakeMode(false);
      setListening(false);
      setVoiceStatus("");
      window.clearTimeout(restartTimerRef.current);
      recognitionRef.current?.stop();
      return;
    }

    wakeModeRef.current = true;
    setWakeMode(true);
    startWakeRecognition();
  }

  function startVoiceInput() {
    if (!SpeechRecognition || disabled || listening) return;

    const recognition = new SpeechRecognition();
    recognition.lang = "fr-FR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setListening(true);
      setVoiceStatus("Eva ecoute");
    };
    recognition.onerror = () => {
      setListening(false);
      setVoiceStatus("");
    };
    recognition.onend = () => {
      setListening(false);
      if (!wakeModeRef.current) {
        setVoiceStatus("");
      }
    };
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
      <div className="voice-toolbar">
        <button
          type="button"
          className={`voice-mode-toggle ${wakeMode ? "active" : ""}`}
          onClick={toggleWakeMode}
          disabled={disabled || !SpeechRecognition}
          title="Activer l'ecoute Eva"
          aria-label="Activer l'ecoute Eva"
        >
          <Radio size={15} aria-hidden="true" />
          {wakeMode ? "Ok Eva actif" : "Wake Eva"}
        </button>
        <button
          type="button"
          className={`voice-mode-toggle ${voiceReplies ? "active" : ""}`}
          onClick={() => onVoiceRepliesChange(!voiceReplies)}
          title="Activer les reponses vocales"
          aria-label="Activer les reponses vocales"
        >
          {voiceReplies ? <Volume2 size={15} aria-hidden="true" /> : <VolumeX size={15} aria-hidden="true" />}
          Voix
        </button>
        {voiceStatus && <span className="voice-status">{voiceStatus}</span>}
      </div>

      <div className="composer">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={wakeMode ? "Dis Ok Eva, puis ta demande..." : "Transmettre a Eva..."}
          rows={1}
          disabled={disabled}
          aria-label="Message pour Eva"
        />
        <button
          type="button"
          className={`voice-button ${listening ? "listening" : ""}`}
          onClick={startVoiceInput}
          disabled={disabled || !SpeechRecognition || wakeMode}
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
