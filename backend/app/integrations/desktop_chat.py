import re

from app.integrations.desktop_automation import (
    DesktopAutomationError,
    click_pixel,
    click_ratio,
    press_hotkey,
    press_key,
)


class DesktopChatError(Exception):
    """Raised when Eva cannot interpret a desktop control request."""


KEY_ALIASES = {
    "enter": "enter",
    "entree": "enter",
    "valider": "enter",
    "espace": "space",
    "space": "space",
    "tab": "tab",
    "echap": "escape",
    "escape": "escape",
    "play": "media_play_pause",
    "pause": "media_play_pause",
    "play pause": "media_play_pause",
    "suivant": "media_next",
    "next": "media_next",
    "precedent": "media_previous",
    "previous": "media_previous",
}


def wants_desktop_control(message: str) -> bool:
    normalized = " ".join(message.lower().split())
    return any(
        marker in normalized
        for marker in (
            "clique",
            "click",
            "appuie",
            "presse",
            "touche",
            "colle",
            "coller",
            "ctrl v",
            "play",
            "pause",
            "suivant",
            "precedent",
        )
    )


def _detect_click(message: str) -> tuple[int, int] | None:
    normalized = message.lower()
    xy_match = re.search(
        r"\bx\s*[=:]?\s*(?P<x>\d{1,5})\D{1,20}\by\s*[=:]?\s*(?P<y>\d{1,5})\b",
        normalized,
    )
    if xy_match:
        return int(xy_match.group("x")), int(xy_match.group("y"))

    pair_match = re.search(
        r"\b(?:clique|click)\D{0,30}(?P<x>\d{2,5})\s*[,; ]\s*(?P<y>\d{2,5})\b",
        normalized,
    )
    if pair_match:
        return int(pair_match.group("x")), int(pair_match.group("y"))

    return None


def execute_desktop_control_from_message(message: str) -> str | None:
    if not wants_desktop_control(message):
        return None

    normalized = " ".join(message.lower().split())

    try:
        if "colle" in normalized or "coller" in normalized or "ctrl v" in normalized:
            result = press_hotkey(("ctrl", "v"))
            return f"Commande clavier envoyee au PC: {result.message}"

        if "clique" in normalized or "click" in normalized:
            coordinates = _detect_click(message)
            if coordinates:
                result = click_pixel(*coordinates)
                return result.message
            if "centre" in normalized or "center" in normalized:
                result = click_ratio(0.5, 0.5)
                return result.message

        for alias, key in KEY_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                result = press_key(key)  # type: ignore[arg-type]
                return f"Commande clavier envoyee au PC: {result.message}"
    except DesktopAutomationError as exc:
        raise DesktopChatError(str(exc)) from exc

    return None
