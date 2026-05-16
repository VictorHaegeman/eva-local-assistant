import shutil
import subprocess
from pathlib import Path

from app.actions.action_store import EvaAction, update_action_status
from app.config import settings
from app.files.local_files import BLOCKED_NAMES, BLOCKED_SUFFIXES, _has_blocked_part
from app.project_factory.executor import (
    execute_clipboard_set_prompt,
    execute_cursor_open_project,
    execute_github_repo_create,
    execute_project_workspace_create,
)
from app.security.action_policy import is_blocked, requires_confirmation


class ActionExecutionError(Exception):
    """Raised when Eva cannot execute an approved local action."""


MAX_READ_CHARS = 120_000


def _resolve_path(path_value: str) -> Path:
    return Path(path_value).expanduser().resolve()


def _execute_command(action: EvaAction) -> str:
    command = str(action.payload.get("command", "")).strip()
    cwd_value = str(action.payload.get("cwd", "")).strip()
    cwd = _resolve_path(cwd_value) if cwd_value else None

    if not command:
        raise ActionExecutionError("Commande vide.")

    if cwd and not cwd.exists():
        raise ActionExecutionError("Dossier de travail introuvable.")

    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        shell=True,
        text=True,
        capture_output=True,
        timeout=settings.eva_action_timeout_seconds,
    )

    output = []
    output.append(f"exit_code={completed.returncode}")
    if completed.stdout:
        output.append("stdout:")
        output.append(completed.stdout[-20_000:])
    if completed.stderr:
        output.append("stderr:")
        output.append(completed.stderr[-20_000:])

    return "\n".join(output).strip()


def _read_file(action: EvaAction) -> str:
    path = _resolve_path(str(action.payload.get("path", "")))

    if not path.exists() or not path.is_file():
        raise ActionExecutionError("Fichier introuvable.")

    if _has_blocked_part(path) or path.name.lower() in BLOCKED_NAMES:
        raise ActionExecutionError("Fichier refuse: chemin sensible bloque.")

    if path.suffix.lower() in BLOCKED_SUFFIXES:
        raise ActionExecutionError("Fichier refuse: type non lisible en texte.")

    content = path.read_bytes().decode("utf-8", errors="replace")
    if len(content) > MAX_READ_CHARS:
        return content[:MAX_READ_CHARS] + "\n\n[TRUNCATED]"

    return content


def _write_file(action: EvaAction) -> str:
    path = _resolve_path(str(action.payload.get("path", "")))
    content = str(action.payload.get("content", ""))
    mode = str(action.payload.get("mode", "overwrite"))

    path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "append":
        with path.open("a", encoding="utf-8") as file:
            file.write(content)
    else:
        path.write_text(content, encoding="utf-8")

    return f"Fichier ecrit: {path}"


def _delete_path(action: EvaAction) -> str:
    path = _resolve_path(str(action.payload.get("path", "")))
    recursive = bool(action.payload.get("recursive", False))

    if not path.exists():
        raise ActionExecutionError("Chemin introuvable.")

    if path.is_dir():
        if not recursive:
            raise ActionExecutionError("Refus: recursive=true requis pour supprimer un dossier.")
        shutil.rmtree(path)
        return f"Dossier supprime: {path}"

    path.unlink()
    return f"Fichier supprime: {path}"


def _codex_prompt(action: EvaAction) -> str:
    prompt = str(action.payload.get("prompt", "")).strip()
    project = str(action.payload.get("project", "")).strip()

    if not prompt:
        raise ActionExecutionError("Prompt Codex/Cursor vide.")

    prefix = f"Projet: {project}\n\n" if project else ""
    return (
        "Prompt pret a donner a Cursor/Codex. Eva ne l'a pas envoye a un service externe.\n\n"
        f"{prefix}{prompt}"
    )


def execute_action(action_id: int, require_approval: bool = True) -> dict[str, object]:
    from app.actions.action_store import action_to_dict, get_action

    if not settings.eva_system_actions_enabled:
        raise ActionExecutionError("Les actions systeme Eva sont desactivees dans .env.")

    action = get_action(action_id)

    if require_approval and action.status != "approved":
        raise ActionExecutionError("Action non approuvee.")

    if is_blocked(action.action_type, action.payload):
        raise ActionExecutionError("Cette action est bloquee par la politique de securite.")

    if not require_approval and requires_confirmation(action.action_type, action.payload):
        raise ActionExecutionError("Cette action est critique et necessite une validation.")

    if not require_approval and action.status == "pending":
        action = update_action_status(action.id, "approved")

    try:
        if action.action_type == "command":
            result = _execute_command(action)
        elif action.action_type == "read_file":
            result = _read_file(action)
        elif action.action_type == "write_file":
            result = _write_file(action)
        elif action.action_type == "delete_path":
            result = _delete_path(action)
        elif action.action_type == "codex_prompt":
            result = _codex_prompt(action)
        elif action.action_type == "project_workspace_create":
            result = execute_project_workspace_create(action)
        elif action.action_type == "clipboard_set_prompt":
            result = execute_clipboard_set_prompt(action)
        elif action.action_type == "cursor_open_project":
            result = execute_cursor_open_project(action)
        elif action.action_type == "github_repo_create":
            result = execute_github_repo_create(action)
        else:
            raise ActionExecutionError(f"Type d'action inconnu: {action.action_type}")
    except Exception as exc:
        failed = update_action_status(action.id, "failed", str(exc))
        return {
            "executed": False,
            "action": action_to_dict(failed),
        }

    executed = update_action_status(action.id, "executed", result)
    return {
        "executed": True,
        "action": action_to_dict(executed),
    }
