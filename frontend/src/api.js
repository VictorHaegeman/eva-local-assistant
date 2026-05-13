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


async function parseResponse(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}


export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/health`);
  const payload = await parseResponse(response);

  if (!response.ok) {
    throw new Error(payload?.detail || "Le backend Eva ne répond pas.");
  }

  return payload;
}


export async function sendChat(messages) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ messages }),
  });

  const payload = await parseResponse(response);

  if (!response.ok) {
    throw new Error(payload?.detail || "Eva ne peut pas répondre pour le moment.");
  }

  return payload.message;
}
