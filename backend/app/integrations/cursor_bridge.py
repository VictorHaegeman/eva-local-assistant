import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
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


def find_cursor_agent() -> str:
    return shutil.which("cursor-agent") or ""


def _start_cursor_agent(project_path: Path, prompt: str) -> dict[str, object]:
    cursor_agent = find_cursor_agent()
    if not cursor_agent:
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
        cursor_agent,
        "-p",
        prompt,
        "--output-format",
        "text",
    ]
    creationflags = 0
    if settings.eva_cursor_agent_background and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        command,
        cwd=str(project_path),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
        creationflags=creationflags,
    )

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
