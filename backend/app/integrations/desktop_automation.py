import ctypes
import subprocess
import time
from dataclasses import dataclass
from typing import Literal

from app.config import settings


class DesktopAutomationError(Exception):
    """Raised when Eva cannot use local keyboard or mouse automation."""


KeyName = Literal[
    "enter",
    "space",
    "tab",
    "escape",
    "media_play_pause",
    "media_next",
    "media_previous",
    "volume_up",
    "volume_down",
    "volume_mute",
]


KEY_CODES: dict[str, int] = {
    "ctrl": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "a": 0x41,
    "c": 0x43,
    "l": 0x4C,
    "v": 0x56,
    "enter": 0x0D,
    "space": 0x20,
    "tab": 0x09,
    "escape": 0x1B,
    "media_play_pause": 0xB3,
    "media_next": 0xB0,
    "media_previous": 0xB1,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "volume_mute": 0xAD,
}

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002


@dataclass(frozen=True)
class DesktopActionResult:
    executed: bool
    message: str


def _ensure_enabled() -> None:
    if not settings.eva_desktop_automation_enabled:
        raise DesktopAutomationError(
            "Automatisation desktop desactivee. Active EVA_DESKTOP_AUTOMATION_ENABLED=true."
        )
    if not hasattr(ctypes, "windll"):
        raise DesktopAutomationError("Automatisation desktop disponible uniquement sur Windows.")


def screen_size() -> tuple[int, int]:
    _ensure_enabled()
    user32 = ctypes.windll.user32
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def click_pixel(x: int, y: int) -> DesktopActionResult:
    _ensure_enabled()
    width, height = screen_size()
    safe_x = max(0, min(int(x), width - 1))
    safe_y = max(0, min(int(y), height - 1))

    user32 = ctypes.windll.user32
    user32.SetCursorPos(safe_x, safe_y)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, safe_x, safe_y, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, safe_x, safe_y, 0, 0)
    return DesktopActionResult(True, f"Clic effectue en pixels: x={safe_x}, y={safe_y}.")


def click_ratio(x_ratio: float, y_ratio: float) -> DesktopActionResult:
    width, height = screen_size()
    x = round(width * max(0.0, min(float(x_ratio), 1.0)))
    y = round(height * max(0.0, min(float(y_ratio), 1.0)))
    return click_pixel(x, y)


def press_key(key: KeyName, presses: int = 1, delay_seconds: float = 0.08) -> DesktopActionResult:
    _ensure_enabled()
    key_code = KEY_CODES.get(key)
    if key_code is None:
        raise DesktopAutomationError(f"Touche non supportee: {key}.")

    user32 = ctypes.windll.user32
    safe_presses = max(1, min(int(presses), 20))
    for _ in range(safe_presses):
        user32.keybd_event(key_code, 0, 0, 0)
        time.sleep(0.03)
        user32.keybd_event(key_code, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(max(float(delay_seconds), 0.0))

    return DesktopActionResult(True, f"Touche envoyee: {key} x{safe_presses}.")


def press_hotkey(keys: tuple[str, ...], delay_seconds: float = 0.08) -> DesktopActionResult:
    _ensure_enabled()
    if not keys:
        raise DesktopAutomationError("Raccourci clavier vide.")

    codes = []
    for key in keys:
        code = KEY_CODES.get(key.strip().lower())
        if code is None:
            raise DesktopAutomationError(f"Touche non supportee dans le raccourci: {key}.")
        codes.append(code)

    user32 = ctypes.windll.user32
    for code in codes:
        user32.keybd_event(code, 0, 0, 0)
        time.sleep(0.02)
    for code in reversed(codes):
        user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)

    time.sleep(max(float(delay_seconds), 0.0))
    label = "+".join(keys)
    return DesktopActionResult(True, f"Raccourci envoye: {label}.")


def set_clipboard_text(text: str) -> DesktopActionResult:
    _ensure_enabled()
    clean_text = text.strip()
    if not clean_text:
        raise DesktopAutomationError("Texte vide: rien a copier dans le presse-papiers.")

    command = "Set-Clipboard -Value ([Console]::In.ReadToEnd())"
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", command],
        input=clean_text,
        text=True,
        capture_output=True,
        timeout=8,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "Set-Clipboard a echoue."
        raise DesktopAutomationError(detail)

    return DesktopActionResult(True, "Texte copie dans le presse-papiers Windows.")


def paste_text(text: str) -> DesktopActionResult:
    set_clipboard_text(text)
    press_hotkey(("ctrl", "v"))
    return DesktopActionResult(True, "Texte colle via Ctrl+V.")


def activate_window(title: str) -> DesktopActionResult:
    _ensure_enabled()
    clean_title = title.strip().replace("'", "''")
    if not clean_title:
        raise DesktopAutomationError("Titre de fenetre vide.")

    command = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$ok = $ws.AppActivate('{clean_title}'); "
        "if ($ok) { exit 0 } else { exit 2 }"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", command],
        text=True,
        capture_output=True,
        timeout=8,
    )
    if completed.returncode != 0:
        return DesktopActionResult(False, f"Fenetre non activee: {title}.")
    return DesktopActionResult(True, f"Fenetre activee: {title}.")


def desktop_status() -> dict[str, object]:
    available = hasattr(ctypes, "windll")
    payload: dict[str, object] = {
        "enabled": settings.eva_desktop_automation_enabled,
        "available": available,
        "local_only": True,
        "supports": [
            "click_pixel",
            "click_ratio",
            "press_key",
            "press_hotkey",
            "clipboard",
            "paste_text",
            "activate_window",
        ],
    }
    if settings.eva_desktop_automation_enabled and available:
        try:
            width, height = screen_size()
            payload["screen"] = {"width": width, "height": height}
        except DesktopAutomationError as exc:
            payload["error"] = str(exc)
    return payload
