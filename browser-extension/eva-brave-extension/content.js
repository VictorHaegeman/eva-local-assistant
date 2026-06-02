(() => {
if (window.__evaBridgeLoaded) {
  return;
}
window.__evaBridgeLoaded = true;

const EVA_API = "http://localhost:8000";
const EVA_MAX_TEXT = 5000;
const EVA_MAX_ELEMENTS = 140;
let evaLastActionId = "";
let evaPendingClickTimer = null;

function isVisible(element) {
  if (!element || !(element instanceof HTMLElement)) return false;
  const style = window.getComputedStyle(element);
  if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return rect.width > 2 && rect.height > 2 && rect.bottom >= 0 && rect.right >= 0 && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
}

function cleanText(value, limit = 180) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
}

function cssSelector(element) {
  if (!(element instanceof HTMLElement)) return "";
  if (element.id) return `#${CSS.escape(element.id)}`;
  const parts = [];
  let node = element;
  while (node && node instanceof HTMLElement && parts.length < 5 && node !== document.body) {
    let part = node.tagName.toLowerCase();
    const testId = node.getAttribute("data-testid") || node.getAttribute("data-test") || node.getAttribute("aria-label");
    if (testId) {
      part += `[${node.hasAttribute("aria-label") ? "aria-label" : node.hasAttribute("data-testid") ? "data-testid" : "data-test"}="${CSS.escape(testId).replace(/"/g, '\\"')}"]`;
      parts.unshift(part);
      break;
    }
    const parent = node.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter((child) => child.tagName === node.tagName);
      if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
    }
    parts.unshift(part);
    node = parent;
  }
  return parts.join(" > ");
}

function elementLabel(element) {
  const tag = element.tagName.toLowerCase();
  const type = element.getAttribute("type") || "";
  const aria = element.getAttribute("aria-label") || "";
  const title = element.getAttribute("title") || "";
  const placeholder = element.getAttribute("placeholder") || "";
  const alt = element.getAttribute("alt") || "";
  const text = cleanText(element.innerText || element.textContent || element.value || "");
  return cleanText([tag, type, aria, title, placeholder, alt, text].filter(Boolean).join(" | "), 260);
}

function ensureEvaVisualStyles() {
  if (document.getElementById("eva-bridge-visual-style")) return;
  const style = document.createElement("style");
  style.id = "eva-bridge-visual-style";
  style.textContent = `
    @keyframes evaBridgePulse {
      0% { opacity: 0.95; transform: translate(-50%, -50%) scale(0.35); }
      55% { opacity: 0.9; transform: translate(-50%, -50%) scale(1); }
      100% { opacity: 0; transform: translate(-50%, -50%) scale(1.7); }
    }
    @keyframes evaBridgeLabel {
      0% { opacity: 0; transform: translateY(4px); }
      18% { opacity: 1; transform: translateY(0); }
      78% { opacity: 1; transform: translateY(0); }
      100% { opacity: 0; transform: translateY(-4px); }
    }
    .eva-bridge-click-pulse {
      position: fixed;
      width: 56px;
      height: 56px;
      border: 2px solid rgba(101, 216, 255, 0.98);
      border-radius: 999px;
      box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.55) inset,
        0 0 22px rgba(101, 216, 255, 0.75),
        0 0 52px rgba(42, 145, 255, 0.35);
      pointer-events: none;
      z-index: 2147483647;
      animation: evaBridgePulse 1150ms cubic-bezier(.2,.9,.25,1) forwards;
    }
    .eva-bridge-click-pulse::after {
      content: "";
      position: absolute;
      inset: 18px;
      border-radius: inherit;
      background: rgba(101, 216, 255, 0.95);
      box-shadow: 0 0 16px rgba(101, 216, 255, 0.95);
    }
    .eva-bridge-click-label {
      position: fixed;
      max-width: 220px;
      padding: 8px 11px;
      border: 1px solid rgba(101, 216, 255, 0.72);
      border-radius: 12px;
      background: linear-gradient(135deg, rgba(6, 28, 43, 0.94), rgba(10, 58, 86, 0.88));
      color: #eaf8ff;
      font: 700 12px/1.2 system-ui, -apple-system, Segoe UI, sans-serif;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45), 0 0 28px rgba(101, 216, 255, 0.22);
      pointer-events: none;
      z-index: 2147483647;
      animation: evaBridgeLabel 1150ms ease-out forwards;
    }
  `;
  document.documentElement.appendChild(style);
}

function showEvaActionBubble(element, text) {
  if (!element || typeof element.getBoundingClientRect !== "function") return;
  ensureEvaVisualStyles();
  const rect = element.getBoundingClientRect();
  const x = Math.max(24, Math.min(window.innerWidth - 24, rect.left + rect.width / 2));
  const y = Math.max(24, Math.min(window.innerHeight - 24, rect.top + rect.height / 2));
  const labelX = Math.max(12, Math.min(window.innerWidth - 180, x + 22));
  const labelY = Math.max(12, Math.min(window.innerHeight - 54, y - 20));

  const pulse = document.createElement("div");
  pulse.className = "eva-bridge-click-pulse";
  pulse.style.left = `${x}px`;
  pulse.style.top = `${y}px`;

  const label = document.createElement("div");
  label.className = "eva-bridge-click-label";
  label.textContent = text;
  label.style.left = `${labelX}px`;
  label.style.top = `${labelY}px`;

  document.documentElement.append(pulse, label);
  window.setTimeout(() => {
    pulse.remove();
    label.remove();
  }, 1300);
}

function collectElements() {
  const selectors = [
    "button",
    "a[href]",
    "input:not([type=hidden])",
    "textarea",
    "select",
    "[role=button]",
    "[role=link]",
    "[role=checkbox]",
    "[role=radio]",
    "[contenteditable=true]",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");

  return Array.from(document.querySelectorAll(selectors))
    .filter(isVisible)
    .slice(0, EVA_MAX_ELEMENTS)
    .map((element, index) => {
      const rect = element.getBoundingClientRect();
      const type = element.getAttribute("type") || "";
      const safeValue = type.toLowerCase() === "password" ? "" : cleanText(element.value || "", 120);
      return {
        index,
        tag: element.tagName.toLowerCase(),
        role: element.getAttribute("role") || "",
        type,
        label: elementLabel(element),
        text: cleanText(element.innerText || element.textContent || "", 220),
        aria: cleanText(element.getAttribute("aria-label") || "", 120),
        placeholder: cleanText(element.getAttribute("placeholder") || "", 120),
        value: safeValue,
        selector: cssSelector(element),
        rect: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        }
      };
    });
}

function collectSnapshot() {
  const visibleText = cleanText(document.body ? document.body.innerText : "", EVA_MAX_TEXT);
  return {
    extension_id: "eva-brave-extension",
    tab_url: window.location.href,
    title: document.title || "",
    visible_text: visibleText,
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      scroll_x: Math.round(window.scrollX),
      scroll_y: Math.round(window.scrollY)
    },
    elements: collectElements(),
    captured_at: new Date().toISOString()
  };
}

function getElement(action) {
  if (action.selector) {
    try {
      const selected = document.querySelector(action.selector);
      if (selected) return selected;
    } catch (_) {
      // Fall through to index lookup.
    }
  }
  const elements = collectElements();
  const item = elements.find((entry) => entry.index === Number(action.element_index));
  if (item && item.selector) {
    try {
      return document.querySelector(item.selector);
    } catch (_) {
      return null;
    }
  }
  return null;
}

function dispatchInput(element) {
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

async function executeAction(action) {
  const name = String(action.action || "none").toLowerCase();
  if (name === "none") return { ok: true, message: "No action." };
  if (name === "wait") {
    await new Promise((resolve) => setTimeout(resolve, 800));
    return { ok: true, message: "Waited." };
  }
  if (name === "scroll") {
    const direction = String(action.direction || "down").toLowerCase();
    const delta = direction === "up" ? -Math.round(window.innerHeight * 0.75) : Math.round(window.innerHeight * 0.75);
    window.scrollBy({ top: delta, behavior: "smooth" });
    return { ok: true, message: `Scrolled ${direction}.` };
  }

  const element = getElement(action);
  if (!element) return { ok: false, message: "Element not found." };
  element.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
  await new Promise((resolve) => setTimeout(resolve, 250));

  if (name === "click") {
    const label = elementLabel(element);
    showEvaActionBubble(element, "Eva clique");
    if (evaPendingClickTimer) {
      window.clearTimeout(evaPendingClickTimer);
    }
    evaPendingClickTimer = window.setTimeout(() => {
      evaPendingClickTimer = null;
      element.click();
    }, 650);
    return { ok: true, message: `Clicked ${label}` };
  }

  if (name === "focus") {
    showEvaActionBubble(element, "Eva cible");
    element.focus();
    return { ok: true, message: `Focused ${elementLabel(element)}` };
  }

  if (name === "set_value") {
    showEvaActionBubble(element, "Eva remplit");
    element.focus();
    const text = String(action.text || "");
    if ("value" in element) {
      element.value = text;
      dispatchInput(element);
      return { ok: true, message: "Value set." };
    }
    element.textContent = text;
    dispatchInput(element);
    return { ok: true, message: "Editable text set." };
  }

  if (name === "key") {
    element.focus();
    const key = String(action.key || "Enter");
    const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
    element.dispatchEvent(event);
    return { ok: true, message: `Key dispatched: ${key}` };
  }

  return { ok: false, message: `Unsupported action: ${name}` };
}

async function postJson(path, payload) {
  const response = await fetch(`${EVA_API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function tick() {
  const settings = await chrome.storage.local.get({ evaEnabled: true });
  if (!settings.evaEnabled) return;

  try {
    const snapshot = collectSnapshot();
    const observe = await postJson("/browser-extension/snapshot", snapshot);
    const tabId = encodeURIComponent(observe.tab_id || snapshot.tab_url);
    const actionResponse = await fetch(`${EVA_API}/browser-extension/next-action?tab_id=${tabId}`);
    if (!actionResponse.ok) return;
    const actionPayload = await actionResponse.json();
    const action = actionPayload.action;
    if (!action || !action.id || action.id === evaLastActionId) return;

    evaLastActionId = action.id;
    const result = await executeAction(action);
    await postJson("/browser-extension/action-result", {
      action_id: action.id,
      tab_id: observe.tab_id || snapshot.tab_url,
      ok: Boolean(result.ok),
      message: result.message || "",
      url: window.location.href,
      title: document.title || "",
      completed_at: new Date().toISOString()
    });
  } catch (_) {
    // Keep the bridge quiet; popup/status shows whether backend is reachable.
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "evaSnapshot") {
    sendResponse(collectSnapshot());
    return true;
  }
  if (message && message.type === "evaExecuteAction") {
    executeAction(message.action || {}).then(sendResponse);
    return true;
  }
  return false;
});

setInterval(tick, 1800);
tick();
})();
