import os
import subprocess
import time
from pathlib import Path

from app.config import settings
from app.integrations.browser import open_url
from app.integrations.desktop_automation import (
    DesktopAutomationError,
    activate_window,
    paste_text,
    set_clipboard_text,
)
from app.llm.ollama_client import OllamaClientError, ask_ollama
from app.screen.screen_reader import ScreenReaderError, analyze_screen


class BeeperAssistantError(Exception):
    """Raised when Eva cannot use Beeper safely."""


BEEPER_MARKERS = ("beeper", "messages", "message", "dm", "inbox")
DEBRIEF_MARKERS = ("debrief", "debriefing", "resume", "resumer", "lis", "lire", "check", "regarde")
REPLY_MARKERS = ("repond", "reponse", "brouillon", "redige", "ecris", "ecrit")

BEEPER_SCREEN_INSTRUCTION = """
Tu lis uniquement ce qui est visible dans Beeper a l'ecran.

Objectif:
1. Resume les conversations visibles et les messages importants.
2. Distingue messages lus/non lus si c'est visible.
3. Liste les personnes ou canaux a traiter en priorite.
4. Propose les reponses utiles, sans pretendre les avoir envoyees.

Contraintes:
- Ne repete pas de token, mot de passe ou code prive si tu en vois un.
- Si le message n'est pas visible, dis clairement qu'il faut ouvrir la conversation.
- Ne clique pas et n'envoie rien: tu analyses seulement l'ecran.
""".strip()


def wants_beeper(message: str) -> bool:
    normalized = " ".join(message.lower().split())
    has_beeper = "beeper" in normalized
    message_request = any(
        marker in normalized
        for marker in ("mes messages", "messages beeper", "message beeper", "mes dm", "ma messagerie")
    )
    action_request = any(marker in normalized for marker in DEBRIEF_MARKERS + REPLY_MARKERS)
    excluded = any(marker in normalized for marker in ("gmail", "telegram", "linkedin", "mail"))
    return has_beeper or (message_request and action_request and not excluded)


def wants_beeper_reply(message: str) -> bool:
    normalized = " ".join(message.lower().split())
    return wants_beeper(message) and any(marker in normalized for marker in REPLY_MARKERS)


def _beeper_exe_candidates() -> list[Path]:
    roots = []
    for env_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value))

    candidates = []
    for root in roots:
        candidates.extend(
            [
                root / "Programs" / "Beeper" / "Beeper.exe",
                root / "Programs" / "beeper" / "Beeper.exe",
                root / "Programs" / "beeper.desktop" / "Beeper.exe",
                root / "Beeper" / "Beeper.exe",
            ]
        )
    return candidates


def _open_start_app() -> bool:
    command = """
$app = Get-StartApps | Where-Object { $_.Name -like '*Beeper*' } | Select-Object -First 1
if ($null -eq $app) { exit 2 }
Start-Process "shell:AppsFolder\\$($app.AppID)"
""".strip()
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", command],
        text=True,
        capture_output=True,
        timeout=10,
    )
    return completed.returncode == 0


def open_beeper() -> dict[str, object]:
    if not settings.eva_beeper_enabled:
        raise BeeperAssistantError("Beeper est desactive. Active EVA_BEEPER_ENABLED=true.")

    for candidate in _beeper_exe_candidates():
        if candidate.exists():
            subprocess.Popen([str(candidate)], shell=False)
            time.sleep(max(settings.eva_beeper_open_delay_seconds, 0.5))
            activated = activate_window("Beeper")
            return {
                "opened": True,
                "target": str(candidate),
                "activated": activated.executed,
                "message": activated.message,
            }

    if _open_start_app():
        time.sleep(max(settings.eva_beeper_open_delay_seconds, 0.5))
        activated = activate_window("Beeper")
        return {
            "opened": True,
            "target": "Windows StartApps",
            "activated": activated.executed,
            "message": activated.message,
        }

    open_url(settings.eva_beeper_web_url, app_mode=True)
    time.sleep(max(settings.eva_beeper_open_delay_seconds, 0.5))
    return {
        "opened": True,
        "target": settings.eva_beeper_web_url,
        "activated": False,
        "message": "Beeper Web ouvert dans le navigateur local.",
    }


async def read_beeper_screen(instruction: str = "") -> dict[str, object]:
    open_result = open_beeper()
    try:
        screen_result = await analyze_screen(
            instruction=f"{BEEPER_SCREEN_INSTRUCTION}\n\nInstruction de Victor:\n{instruction}".strip(),
            auto_fix=True,
        )
    except ScreenReaderError as exc:
        raise BeeperAssistantError(str(exc)) from exc

    return {
        "open": open_result,
        "screen": screen_result,
    }


async def _draft_beeper_reply(user_message: str, screen_analysis: str) -> str:
    prompt = f"""
Tu es Eva. Victor veut repondre dans Beeper.

Tu dois produire uniquement un brouillon de message court, pret a coller.
N'envoie rien. Ne dis pas que le message est envoye.
Si l'ecran ne montre pas assez de contexte, pose une question courte au lieu d'inventer.

Demande de Victor:
{user_message}

Analyse visible de Beeper:
{screen_analysis}

Brouillon a copier:
""".strip()
    try:
        return await ask_ollama([{"role": "user", "content": prompt}])
    except OllamaClientError as exc:
        raise BeeperAssistantError(str(exc)) from exc


async def build_beeper_chat_response(message: str) -> str | None:
    if not wants_beeper(message):
        return None

    payload = await read_beeper_screen(message)
    open_result = payload["open"]
    screen = payload["screen"]
    analysis = str(screen.get("analysis", "")).strip()

    lines = [
        "Source: Beeper desktop/web + lecture pixels locale.",
        f"Ouverture: {open_result.get('message', '')}",
        "",
        "Debrief visible:",
        analysis or "Aucune analyse exploitable renvoyee par le modele vision.",
    ]
    terminal_diagnosis = screen.get("terminal_diagnosis")
    if isinstance(terminal_diagnosis, dict) and terminal_diagnosis.get("detected"):
        lines.extend(
            [
                "",
                "Diagnostic terminal detecte a l'ecran:",
                str(terminal_diagnosis.get("title", "Erreur terminal detectee.")),
                str(terminal_diagnosis.get("cause", "")),
            ]
        )
        fix = terminal_diagnosis.get("fix")
        if isinstance(fix, dict):
            lines.append(f"Correctif propose: {fix.get('label', fix.get('key', 'correctif connu'))}")
        launched = screen.get("launched")
        if isinstance(launched, dict):
            lines.extend(
                [
                    "Correctif local lance automatiquement:",
                    str(launched.get("message", launched)),
                ]
            )

    if wants_beeper_reply(message):
        draft = await _draft_beeper_reply(message, analysis)
        try:
            if settings.eva_beeper_auto_paste_draft:
                paste_result = paste_text(draft)
                lines.extend(
                    [
                        "",
                        "Brouillon Beeper prepare et colle dans la fenetre active.",
                        paste_result.message,
                        "Je n'ai pas appuye sur Envoyer.",
                    ]
                )
            else:
                clipboard_result = set_clipboard_text(draft)
                lines.extend(
                    [
                        "",
                        "Brouillon Beeper prepare dans le presse-papiers.",
                        clipboard_result.message,
                        "Clique dans la conversation Beeper puis fais Ctrl+V, ou demande-moi de cliquer/coller sur une zone precise.",
                    ]
                )
        except DesktopAutomationError as exc:
            raise BeeperAssistantError(str(exc)) from exc

        lines.extend(["", "Brouillon:", draft])

    return "\n".join(lines)
