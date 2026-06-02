const EVA_API = "http://localhost:8000";

const statusDot = document.getElementById("statusDot");
const statusLabel = document.getElementById("statusLabel");
const toggleButton = document.getElementById("toggleButton");
const instruction = document.getElementById("instruction");
const runButton = document.getElementById("runButton");
const result = document.getElementById("result");

async function refreshToggle() {
  const state = await chrome.storage.local.get({ evaEnabled: true });
  toggleButton.textContent = state.evaEnabled ? "Actif" : "Pause";
  toggleButton.dataset.enabled = String(state.evaEnabled);
}

async function refreshStatus() {
  try {
    const response = await fetch(`${EVA_API}/browser-extension/status`);
    if (!response.ok) throw new Error(`${response.status}`);
    const payload = await response.json();
    statusDot.classList.add("ok");
    const age = payload.latest_age_seconds;
    statusLabel.textContent = payload.connected
      ? `Connecté${typeof age === "number" ? ` (${Math.round(age)}s)` : ""}`
      : "Backend OK, page non vue";
  } catch (error) {
    statusDot.classList.remove("ok");
    statusLabel.textContent = "Backend indisponible";
  }
}

toggleButton.addEventListener("click", async () => {
  const state = await chrome.storage.local.get({ evaEnabled: true });
  await chrome.storage.local.set({ evaEnabled: !state.evaEnabled });
  await refreshToggle();
});

runButton.addEventListener("click", async () => {
  const text = instruction.value.trim() || "Continue l'exercice visible en mode entrainement";
  result.textContent = "Eva prend le relais sur la page visible...";
  try {
    const response = await fetch(`${EVA_API}/browser-extension/training`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction: text, max_rounds: 14 })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || response.statusText);
    result.textContent = payload.summary || `Statut: ${payload.status}`;
  } catch (error) {
    result.textContent = `Erreur: ${error.message || error}`;
  }
});

refreshToggle();
refreshStatus();
setInterval(refreshStatus, 2000);
