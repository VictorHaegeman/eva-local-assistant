import shutil
import subprocess
from pathlib import Path

from app.config import settings
from app.projects.project_store import build_cursor_prompt, get_project


class CursorBridgeError(Exception):
    """Raised when Eva cannot prepare a local Cursor work session."""


PROMPT_FILE_NAME = "EVA_CURSOR_PROMPT.md"


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

    return {
        "project": project,
        "prompt": prompt,
        "prompt_file": str(prompt_file) if prompt_file else "",
        "copied_to_clipboard": copied,
        "cursor_opened": opened,
        "cursor_cli": cursor_path,
    }
