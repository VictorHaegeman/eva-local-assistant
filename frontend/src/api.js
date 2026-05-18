function getApiBaseUrl() {
  const configuredUrl = import.meta.env.VITE_API_BASE_URL;
  if (configuredUrl) {
    return configuredUrl.replace(/\/$/, "");
  }

  if (typeof window !== "undefined" && window.location.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  return "http://127.0.0.1:8000";
}


const API_BASE_URL = getApiBaseUrl();
const EVA_API_TOKEN = import.meta.env.VITE_EVA_API_TOKEN || "";


async function parseResponse(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}


async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (EVA_API_TOKEN && !headers.has("X-Eva-Api-Token")) {
    headers.set("X-Eva-Api-Token", EVA_API_TOKEN);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
  const payload = await parseResponse(response);

  if (!response.ok) {
    throw new Error(payload?.detail || "Eva ne peut pas charger cette section.");
  }

  return payload;
}


export async function getHealth() {
  return request("/health");
}


export async function getDoctor() {
  return request("/doctor");
}


export async function getModes() {
  const payload = await request("/agents/modes");
  return payload.modes || [];
}


export async function getTools() {
  return request("/tools");
}


export async function getSkills() {
  return request("/skills");
}


export async function getAutonomy() {
  return request("/autonomy");
}


export async function getScreenStatus() {
  return request("/screen/status");
}


export async function analyzeScreen(instruction = "", autoFix = true) {
  return request("/screen/analyze", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ instruction, auto_fix: autoFix }),
  });
}


export async function getMemories() {
  return request("/memories");
}


export async function getChatHistory() {
  return request("/chat/history");
}


export async function getChatHistoryMessages(sessionId) {
  return request(`/chat/history/${encodeURIComponent(sessionId)}`);
}


export async function getObsidianMemoryStatus() {
  return request("/memory/obsidian/status");
}


export async function syncObsidianMemory() {
  return request("/memory/obsidian/sync", {
    method: "POST",
  });
}


export async function getProjects() {
  return request("/projects");
}


export async function planProjectFactory(idea, projectName = "") {
  return request("/project-factory/plan", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ idea, project_name: projectName }),
  });
}


export async function createProjectFactoryActions(idea, projectName = "") {
  return request("/project-factory/actions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ idea, project_name: projectName }),
  });
}


export async function getActions(status = "") {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/actions${query}`);
}


export async function getHeartbeatStatus() {
  return request("/heartbeat/status");
}


export async function runHeartbeat(jobKey) {
  return request(`/heartbeat/run/${encodeURIComponent(jobKey)}`, {
    method: "POST",
  });
}


export async function getGmailStatus() {
  return request("/gmail/status");
}


export async function connectGmail(forceReconnect = false) {
  const query = forceReconnect ? "?force_reconnect=true" : "";
  return request(`/gmail/connect${query}`, {
    method: "POST",
  });
}


export async function getGmailMessages() {
  return request("/gmail/messages?max_results=5");
}


export async function getLinkedInStatus() {
  return request("/linkedin/status");
}


export async function getLatestBrief() {
  return request("/brief/latest");
}


export async function generateSmartBrief() {
  return request("/brief/smart", {
    method: "POST",
  });
}


export async function getDailyLaunchBrief(force = false) {
  return request("/brief/daily-launch", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ force }),
  });
}


export async function openBrowserTabs(urls) {
  return request("/browser/open-tabs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ urls }),
  });
}


export async function sendChat(messages, mode = "chat", sessionId = "") {
  return request("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ messages, mode, session_id: sessionId }),
  });
}
