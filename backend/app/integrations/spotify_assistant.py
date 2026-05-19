import os
import re
import time
import unicodedata
from urllib.parse import quote, quote_plus

from app.config import settings
from app.integrations.browser import open_url
from app.integrations.desktop_automation import (
    DesktopAutomationError,
    activate_window,
    click_ratio,
    press_key,
)


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
    "cherche",
    "trouve",
)
PAUSE_MARKERS = ("pause", "stop", "arrete", "arreter")
NEXT_MARKERS = ("suivant", "next", "prochaine")
PREVIOUS_MARKERS = ("precedent", "precedente", "previous", "retour")


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
        r"\b(?:lance|mets|met|joue|play|ecoute|cherche|trouve)\b",
        r"\b(?:une|un|la|le|des|de|du|musique|chanson|son|titre|morceau)\b",
        r"\bstp\b",
        r"\bs'il te plait\b",
    )
    for pattern in cleanup_patterns:
        query = re.sub(pattern, " ", query, flags=re.IGNORECASE)
    return " ".join(query.strip(" :,-").split())


def detect_spotify_request(message: str) -> dict[str, str] | None:
    normalized = _normalize(message)
    spotify_context = any(marker in normalized for marker in SPOTIFY_MARKERS)
    media_context = any(marker in normalized for marker in PAUSE_MARKERS + NEXT_MARKERS + PREVIOUS_MARKERS)
    if not spotify_context and not media_context:
        return None

    if any(marker in normalized for marker in NEXT_MARKERS):
        return {
            "kind": "media",
            "query": "",
            "media_action": "media_next",
            "spotify_uri": "",
            "web_url": "",
        }

    if any(marker in normalized for marker in PREVIOUS_MARKERS):
        return {
            "kind": "media",
            "query": "",
            "media_action": "media_previous",
            "spotify_uri": "",
            "web_url": "",
        }

    if any(marker in normalized for marker in PAUSE_MARKERS):
        return {
            "kind": "media",
            "query": "",
            "media_action": "media_play_pause",
            "spotify_uri": "",
            "web_url": "",
        }

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


def _attempt_spotify_ui_play(opened_app: bool) -> list[str]:
    if not opened_app or not settings.eva_spotify_auto_ui_enabled:
        return []

    notes: list[str] = []
    try:
        time.sleep(max(settings.eva_spotify_ui_delay_seconds, 0.5))
        activated = activate_window("Spotify")
        notes.append(activated.message)
        time.sleep(0.3)

        # Spotify does not expose a free local API for playback. This is a pragmatic
        # UI attempt: focus the first visible result, activate it, then send media play.
        click_result = click_ratio(0.42, 0.38)
        notes.append(click_result.message)
        time.sleep(0.2)
        notes.append(press_key("enter").message)
        time.sleep(0.4)
        notes.append(press_key("media_play_pause").message)
    except (DesktopAutomationError, OSError) as exc:
        notes.append(f"Automation Spotify incomplete: {exc}")
    return notes


def open_spotify_from_message(message: str) -> str | None:
    request = detect_spotify_request(message)
    if not request:
        return None

    if request["kind"] == "media":
        try:
            result = press_key(request["media_action"])  # type: ignore[arg-type]
        except DesktopAutomationError as exc:
            raise SpotifyAssistError(str(exc)) from exc
        return f"Commande media envoyee au PC: {result.message}"

    opened_app = _open_spotify_uri(request["spotify_uri"])
    if not opened_app:
        open_url(request["web_url"])

    if request["kind"] == "search":
        notes = _attempt_spotify_ui_play(opened_app)
        target = "l'app Spotify" if opened_app else "Spotify Web dans Brave"
        note_block = "\n".join(f"- {note}" for note in notes)
        action_line = (
            "\n\nControle PC tente:\n" + note_block
            if note_block
            else "\n\nJ'ai ouvert la recherche. Spotify peut encore demander un clic Play selon ta session."
        )
        return (
            f"J'ai ouvert {target} sur la recherche: {request['query']}.\n"
            f"{action_line}"
        )

    target = "l'app Spotify" if opened_app else "Spotify Web dans Brave"
    return f"J'ai ouvert {target}."
