const EVA_API = "http://localhost:8000";

const statusDot = document.getElementById("statusDot");
const statusLabel = document.getElementById("statusLabel");
const toggleButton = document.getElementById("toggleButton");
const instruction = document.getElementById("instruction");
const runButton = document.getElementById("runButton");
const result = document.getElementById("result");

let lastSyncAt = 0;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs && tabs.length ? tabs[0] : null;
}

function canInject(tab) {
  const url = String((tab && tab.url) || "");
  return /^https?:\/\//i.test(url) || /^file:\/\//i.test(url);
}

function askTabForSnapshot(tabId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, { type: "evaSnapshot" }, (snapshot) => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }
      if (!snapshot || !snapshot.tab_url) {
        reject(new Error("Snapshot vide"));
        return;
      }
      resolve(snapshot);
    });
  });
}

async function injectBridge(tab) {
  if (!canInject(tab)) {
    throw new Error("Page Brave non pilotable par extension");
  }
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["content.js"]
  });
  await sleep(250);
}

async function syncActivePage(options = {}) {
  const now = Date.now();
  if (!options.force && now - lastSyncAt < 1200) {
    return null;
  }
  lastSyncAt = now;

  const state = await chrome.storage.local.get({ evaEnabled: true });
  if (!state.evaEnabled) {
    throw new Error("Bridge en pause");
  }

  const tab = await activeTab();
  if (!tab || !tab.id) {
    throw new Error("Aucun onglet actif");
  }

  let snapshot;
  try {
    snapshot = await askTabForSnapshot(tab.id);
  } catch (_) {
    await injectBridge(tab);
    snapshot = await askTabForSnapshot(tab.id);
  }

  const response = await fetch(`${EVA_API}/browser-extension/snapshot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(snapshot)
  });
  if (!response.ok) {
    throw new Error(`Backend snapshot ${response.status}`);
  }
  return response.json();
}

async function refreshToggle() {
  const state = await chrome.storage.local.get({ evaEnabled: true });
  toggleButton.textContent = state.evaEnabled ? "Actif" : "Pause";
  toggleButton.dataset.enabled = String(state.evaEnabled);
}

async function refreshStatus() {
  try {
    await syncActivePage().catch(() => null);
    const response = await fetch(`${EVA_API}/browser-extension/status`);
    if (!response.ok) throw new Error(`${response.status}`);
    const payload = await response.json();
    statusDot.classList.add("ok");
    const age = payload.latest_age_seconds;
    statusLabel.textContent = payload.connected
      ? `Connecte${typeof age === "number" ? ` (${Math.round(age)}s)` : ""}`
      : "Backend OK, page non vue";
  } catch (_) {
    statusDot.classList.remove("ok");
    statusLabel.textContent = "Backend indisponible";
  }
}

toggleButton.addEventListener("click", async () => {
  const state = await chrome.storage.local.get({ evaEnabled: true });
  await chrome.storage.local.set({ evaEnabled: !state.evaEnabled });
  await refreshToggle();
  await refreshStatus();
});

runButton.addEventListener("click", async () => {
  const text = instruction.value.trim() || "Continue l'exercice visible en mode entrainement";
  result.textContent = "Synchronisation de l'onglet actif...";
  try {
    await syncActivePage({ force: true });
    result.textContent = "Eva prend le relais sur la page visible...";
    const response = await fetch(`${EVA_API}/browser-extension/training`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction: text, max_rounds: 24 })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || response.statusText);
    result.textContent = payload.summary || `Statut: ${payload.status}`;
    await refreshStatus();
  } catch (error) {
    result.textContent = `Erreur: ${error.message || error}`;
  }
});

refreshToggle();
refreshStatus();
setInterval(refreshStatus, 2000);
