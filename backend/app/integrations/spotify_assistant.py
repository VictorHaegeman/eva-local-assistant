import os
import re
import unicodedata
from urllib.parse import quote, quote_plus

from app.integrations.browser import open_url


class SpotifyAssistError(Exception):
    """Raised when Eva cannot prepare a Spotify action."""


SPOTIFY_MARKERS = ("spotify", "spotif", "spotifi")
PLAY_MARKERS = (
    "lance",
    "mets",
    "met",
    "joue",
    "play",
    "ecoute",
    "écoute",
    "cherche",
    "trouve",
)


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _open_spotify_uri(uri: str) -> bool:
    if os.name != "nt":
        return False

    try:
        os.startfile(uri)  # type: ignore[attr-defined]
        return True
    except OSError:
        return False


def _clean_query(message: str) -> str:
    query = message.strip()
    cleanup_patterns = (
        r"\b(?:ouvre|ouvrir|open)\s+spotify\b",
        r"\b(?:sur|dans)\s+spotify\b",
        r"\bspotify\b",
        r"\b(?:lance|mets|met|joue|play|ecoute|écoute|cherche|trouve)\b",
        r"\b(?:une|un|la|le|des|de|du|musique|chanson|son|titre|morceau)\b",
        r"\bstp\b",
        r"\bs'il te plait\b",
        r"\bs'il te plaît\b",
    )
    for pattern in cleanup_patterns:
        query = re.sub(pattern, " ", query, flags=re.IGNORECASE)
    return " ".join(query.strip(" :,-").split())


def detect_spotify_request(message: str) -> dict[str, str] | None:
    normalized = _normalize(message)
    if not any(marker in normalized for marker in SPOTIFY_MARKERS):
        return None

    query = _clean_query(message)
    if query and any(marker in normalized for marker in PLAY_MARKERS):
        encoded_uri_query = quote(query, safe="")
        encoded_web_query = quote_plus(query)
        return {
            "kind": "search",
            "query": query,
            "spotify_uri": f"spotify:search:{encoded_uri_query}",
            "web_url": f"https://open.spotify.com/search/{encoded_web_query}",
        }

    return {
        "kind": "open",
        "query": "",
        "spotify_uri": "spotify:",
        "web_url": "https://open.spotify.com",
    }


def open_spotify_from_message(message: str) -> str | None:
    request = detect_spotify_request(message)
    if not request:
        return None

    opened_app = _open_spotify_uri(request["spotify_uri"])
    if not opened_app:
        open_url(request["web_url"])

    if request["kind"] == "search":
        target = "l'app Spotify" if opened_app else "Spotify Web dans Brave"
        return (
            f"J'ai ouvert {target} sur la recherche: {request['query']}.\n"
            "Spotify peut demander un clic sur Play selon ta session et l'appareil actif."
        )

    target = "l'app Spotify" if opened_app else "Spotify Web dans Brave"
    return f"J'ai ouvert {target}."
