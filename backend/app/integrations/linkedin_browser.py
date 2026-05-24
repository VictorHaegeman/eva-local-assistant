import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from app.actions.action_store import EvaAction
from app.config import settings
from app.integrations.browser import open_url


class LinkedInBrowserError(Exception):
    """Raised when Eva cannot prepare LinkedIn in the local browser."""


DEFAULT_LINKEDIN_COMPOSE_URL = "https://www.linkedin.com/feed/?shareActive=true"


def _set_clipboard(text: str) -> None:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Set-Clipboard"],
        input=text,
        text=True,
        capture_output=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise LinkedInBrowserError(completed.stderr or "Impossible de copier le post LinkedIn.")


def _open_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc.endswith("linkedin.com"):
        raise LinkedInBrowserError("URL LinkedIn refusee: seule une URL https linkedin.com est autorisee.")

    open_url(url)


def _send_keys(keys: str) -> None:
    command = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$ws.SendKeys('{keys}')"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        text=True,
        capture_output=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise LinkedInBrowserError(
            completed.stderr or "Impossible d'envoyer les touches au navigateur."
        )


def _auto_fill_composer() -> bool:
    if not settings.eva_linkedin_auto_fill_composer:
        return False

    delay = max(settings.eva_linkedin_auto_fill_delay_seconds, 1.0)
    time.sleep(delay)
    _send_keys("^v")
    return True


def execute_linkedin_browser_prepare_post(action: EvaAction) -> str:
    post_text = str(action.payload.get("post_text", "")).strip()
    target_url = str(action.payload.get("target_url", "")).strip() or DEFAULT_LINKEDIN_COMPOSE_URL
    image_prompt = str(action.payload.get("image_prompt", "")).strip()
    image_path = str(action.payload.get("image_path", "")).strip()

    if not post_text:
        raise LinkedInBrowserError("Post LinkedIn vide.")

    _set_clipboard(post_text)
    _open_url(target_url)
    auto_filled = _auto_fill_composer()

    lines = [
        (
            "Post LinkedIn colle automatiquement dans le compositeur."
            if auto_filled
            else "Post LinkedIn prepare dans le presse-papiers."
        ),
        f"LinkedIn ouvert: {target_url}",
        "Rien n'a ete publie automatiquement.",
        (
            "Relis, ajoute l'image si utile, puis publie seulement quand c'est valide."
            if auto_filled
            else "Colle le texte dans LinkedIn, relis, ajoute l'image si utile, puis publie seulement quand c'est valide."
        ),
    ]

    if image_path:
        path = Path(image_path).expanduser().resolve()
        lines.append(f"Image proposee: {path}")
        if path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)], shell=False)
        else:
            lines.append("Image introuvable localement.")

    if image_prompt:
        lines.append("")
        lines.append("Prompt image propose:")
        lines.append(image_prompt)

    return "\n".join(lines)
