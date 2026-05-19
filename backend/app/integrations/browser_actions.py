import re
import unicodedata
from urllib.parse import urlparse

from app.integrations.browser import open_url


class BrowserActionError(Exception):
    """Raised when Eva cannot safely open a browser target."""


OPEN_MARKERS = (
    "ouvre",
    "ouvrir",
    "open",
    "lance",
    "va sur",
    "vas sur",
    "affiche",
)

BLOCKED_SCHEMES = ("file", "javascript", "data")

SITE_ALIASES = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "calendar": "https://calendar.google.com",
    "calendrier": "https://calendar.google.com",
    "linkedin": "https://www.linkedin.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "dreamlense": "https://dreamlense-ai.com",
}


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _extract_url(text: str) -> str:
    match = re.search(r"https?://[^\s]+", text, flags=re.IGNORECASE)
    if match:
        return match.group(0).rstrip(".,;")

    domain_match = re.search(
        r"\b([a-z0-9-]+\.(?:com|fr|net|org|io|ai|dev|app|co)(?:/[^\s]*)?)\b",
        text,
        flags=re.IGNORECASE,
    )
    if domain_match:
        return f"https://{domain_match.group(1).rstrip('.,;')}"

    return ""


def _safe_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in BLOCKED_SCHEMES or scheme not in {"http", "https"}:
        raise BrowserActionError("URL refusee: Eva ouvre seulement des pages web http/https.")
    if not parsed.netloc:
        raise BrowserActionError("URL refusee: domaine absent.")
    return url


def detect_browser_open_url(message: str) -> str | None:
    normalized = _normalize(message)
    if not any(marker in normalized for marker in OPEN_MARKERS):
        return None

    # Gmail, LinkedIn and project/Cursor have specialized handlers with richer behavior.
    if any(marker in normalized for marker in ("mail", "gmail", "linkedin", "cursor", "codex", "projet")):
        return None

    for alias, url in SITE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return url

    explicit_url = _extract_url(message)
    if explicit_url:
        return explicit_url

    return None


def open_browser_from_message(message: str) -> str | None:
    url = detect_browser_open_url(message)
    if not url:
        return None

    safe_url = _safe_url(url)
    open_url(safe_url)
    return f"J'ai ouvert {safe_url} dans le navigateur local."
