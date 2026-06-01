import subprocess
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import settings
from app.integrations.cli_tools import find_cursor_agent, find_cursor_agent_command
from app.projects.project_store import build_cursor_prompt, get_project


class CursorBridgeError(Exception):
    """Raised when Eva cannot prepare a local Cursor work session."""


PROMPT_FILE_NAME = "EVA_CURSOR_PROMPT.md"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
CURSOR_AGENT_LOG_DIR = DATA_DIR / "cursor_agent_logs"


def _set_clipboard(text: str) -> None:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Set-Clipboard"],
        input=text,
        text=True,
        capture_output=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise CursorBridgeError(completed.stderr or "Impossible de copier le prompt Cursor.")


def _write_prompt_file(project_path: Path, prompt: str) -> Path:
    target = (project_path / PROMPT_FILE_NAME).resolve()
    try:
        target.relative_to(project_path.resolve())
    except ValueError as exc:
        raise CursorBridgeError("Chemin prompt refuse: il sort du projet.") from exc

    target.write_text(
        "# Prompt Eva pour Cursor/Codex\n\n"
        "Ce fichier est genere localement par Eva pour te donner le contexte de travail.\n\n"
        "```text\n"
        f"{prompt}\n"
        "```\n",
        encoding="utf-8",
    )
    return target


def _open_cursor(project_path: Path) -> str:
    cursor = shutil.which("cursor")
    if not cursor:
        raise CursorBridgeError("Cursor CLI introuvable dans le PATH.")

    subprocess.Popen([cursor, str(project_path)], shell=False)
    return cursor


def _notify_telegram_sync(message: str) -> None:
    token = settings.eva_telegram_bot_token.strip()
    chat_id = settings.eva_telegram_allowed_chat_id.strip()
    if not settings.eva_telegram_enabled or not token or not chat_id:
        return

    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message[:3500]},
            timeout=15.0,
        )
    except Exception:
        pass


def _watch_agent_process(
    process: subprocess.Popen[str],
    log_file: object,
    log_path: Path,
    project_name: str,
) -> None:
    try:
        return_code = process.wait()
    finally:
        close = getattr(log_file, "close", None)
        if close:
            close()

    status = "termine" if return_code == 0 else "termine avec erreur"
    _notify_telegram_sync(
        f"Cursor Agent {status} pour {project_name}.\n"
        f"Code retour: {return_code}\n"
        f"Log local: {log_path}"
    )


def _start_cursor_agent(project_path: Path, prompt: str) -> dict[str, object]:
    cursor_agent_command = find_cursor_agent_command()
    if not cursor_agent_command:
        return {
            "available": False,
            "started": False,
            "log_path": "",
            "message": "cursor-agent introuvable dans le PATH.",
        }

    CURSOR_AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    log_path = CURSOR_AGENT_LOG_DIR / f"{project_path.name}-{timestamp}.log"
    log_file = log_path.open("w", encoding="utf-8")

    command = [
        *cursor_agent_command,
        "-p",
        prompt,
        "--output-format",
        "text",
    ]
    creationflags = 0
    if settings.eva_cursor_agent_background and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        process = subprocess.Popen(
            command,
            cwd=str(project_path),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            creationflags=creationflags,
        )
    except OSError:
        log_file.close()
        raise

    threading.Thread(
        target=_watch_agent_process,
        args=(process, log_file, log_path, project_path.name),
        daemon=True,
    ).start()

    return {
        "available": True,
        "started": True,
        "log_path": str(log_path),
        "message": "cursor-agent lance en arriere-plan.",
    }


def prepare_cursor_work_session(project_name: str, task: str) -> dict[str, object]:
    project = get_project(project_name)
    project_path = Path(project["path"]).resolve()
    prompt = build_cursor_prompt(project_name, task)

    prompt_file = None
    if settings.eva_cursor_write_prompt_file:
        prompt_file = _write_prompt_file(project_path, prompt)

    copied = False
    if settings.eva_cursor_auto_copy_prompt:
        _set_clipboard(prompt)
        copied = True

    cursor_path = ""
    opened = False
    if settings.eva_cursor_auto_open_project:
        cursor_path = _open_cursor(project_path)
        opened = True

    agent = {
        "available": bool(find_cursor_agent()),
        "started": False,
        "log_path": "",
        "message": "cursor-agent non lance.",
    }
    if settings.eva_cursor_agent_enabled:
        agent = _start_cursor_agent(project_path, prompt)

    return {
        "project": project,
        "prompt": prompt,
        "prompt_file": str(prompt_file) if prompt_file else "",
        "copied_to_clipboard": copied,
        "cursor_opened": opened,
        "cursor_cli": cursor_path,
        "cursor_agent": agent,
    }
