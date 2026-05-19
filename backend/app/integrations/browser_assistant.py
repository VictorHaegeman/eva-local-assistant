import re
import unicodedata
from urllib.parse import quote_plus

from app.integrations.browser import open_url


class BrowserAssistError(Exception):
    """Raised when Eva cannot open a helpful browser destination."""


VIDEO_MARKERS = (
    "video",
    "tuto",
    "tutoriel",
    "demo",
    "demonstration",
    "montre moi",
    "montre-moi",
    "regarde une video",
    "cherche une video",
    "trouve une video",
    "ouvre une video",
    "ouvre youtube pour",
)

BROWSER_SEARCH_MARKERS = (
    "ouvre un navigateur pour",
    "ouvre le navigateur pour",
    "ouvre brave pour",
    "lance une recherche sur",
    "ouvre une recherche sur",
    "cherche et ouvre",
    "va chercher sur internet",
    "ouvre des onglets sur",
    "ouvre une page sur",
)


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _strip_markers(message: str, markers: tuple[str, ...]) -> str:
    query = message.strip()
    normalized = _normalize(query)
    for marker in sorted(markers, key=len, reverse=True):
        clean_marker = _normalize(marker)
        if clean_marker not in normalized:
            continue

        start = normalized.find(clean_marker)
        if start < 0:
            continue

        # Fallback simple: remove likely trigger words from the original text.
        query = re.sub(re.escape(marker), "", query, flags=re.IGNORECASE).strip(" :,-")

    cleanup_words = (
        "sur youtube",
        "youtube",
        "une video",
        "une vidéo",
        "video",
        "vidéo",
        "un tuto",
        "tuto",
        "tutoriel",
        "montre moi",
        "montre-moi",
        "stp",
        "s'il te plait",
        "s'il te plaît",
    )
    for word in cleanup_words:
        query = re.sub(rf"\b{re.escape(word)}\b", "", query, flags=re.IGNORECASE).strip(" :,-")

    query = re.sub(r"^(?:pour|sur|de|d'|un|une|le|la|les)\s+", "", query, flags=re.IGNORECASE).strip(" :,-")

    return " ".join(query.split()) or message.strip()


def detect_browser_assist(message: str) -> dict[str, str] | None:
    normalized = _normalize(message)

    if any(marker in normalized for marker in VIDEO_MARKERS):
        query = _strip_markers(message, VIDEO_MARKERS)
        return {
            "kind": "video",
            "query": query,
            "url": f"https://www.youtube.com/results?search_query={quote_plus(query)}",
        }

    if any(marker in normalized for marker in BROWSER_SEARCH_MARKERS):
        query = _strip_markers(message, BROWSER_SEARCH_MARKERS)
        return {
            "kind": "browser_search",
            "query": query,
            "url": f"https://www.google.com/search?q={quote_plus(query)}",
        }

    return None


def open_assisted_browser_from_message(message: str) -> str | None:
    assist = detect_browser_assist(message)
    if not assist:
        return None

    url = assist["url"]
    open_url(url)

    if assist["kind"] == "video":
        return (
            f"J'ai ouvert une recherche YouTube dans Brave pour: {assist['query']}.\n"
            "C'est le meilleur format si tu veux voir une demonstration ou un tutoriel."
        )

    return f"J'ai ouvert une recherche web dans Brave pour: {assist['query']}."
