import shutil
import subprocess
from pathlib import Path

from app.actions.action_store import EvaAction, update_action_status
from app.config import settings
from app.files.local_files import LocalFileError, load_allowed_roots, read_text_file
from app.integrations.linkedin_browser import execute_linkedin_browser_prepare_post
from app.project_factory.executor import (
    execute_clipboard_set_prompt,
    execute_cursor_open_project,
    execute_git_initial_commit,
    execute_git_push,
    execute_github_repo_create,
    execute_project_workspace_create,
)
from app.security.action_policy import can_auto_execute, is_blocked


class ActionExecutionError(Exception):
    """Raised when Eva cannot execute an approved local action."""


def _resolve_path(path_value: str) -> Path:
    return Path(path_value).expanduser().resolve()


def _path_in_allowed_roots(path: Path) -> bool:
    try:
        roots = load_allowed_roots()
    except LocalFileError as exc:
        raise ActionExecutionError(str(exc)) from exc

    for root in roots:
        try:
            path.relative_to(root.path)
            return True
        except ValueError:
            continue
    return False


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
    root_name = str(action.payload.get("root", "")).strip()
    relative_path = str(action.payload.get("relative_path") or action.payload.get("path", "")).strip()

    try:
        if root_name:
            payload = read_text_file(root_name, relative_path)
            return str(payload["content"])

        absolute_path = _resolve_path(relative_path)
        for root in load_allowed_roots():
            try:
                path_in_root = absolute_path.relative_to(root.path)
            except ValueError:
                continue

            payload = read_text_file(root.name, path_in_root.as_posix())
            return str(payload["content"])
    except LocalFileError as exc:
        raise ActionExecutionError(str(exc)) from exc

    raise ActionExecutionError("Lecture refusee: chemin hors dossiers autorises.")


def _write_file(action: EvaAction) -> str:
    path = _resolve_path(str(action.payload.get("path", "")))
    content = str(action.payload.get("content", ""))
    mode = str(action.payload.get("mode", "overwrite"))

    if not settings.eva_allow_write_any_path and not _path_in_allowed_roots(path):
        raise ActionExecutionError(
            "Ecriture refusee: chemin hors dossiers autorises. "
            "Ajoute le dossier dans data/eva_allowed_paths.json ou active EVA_ALLOW_WRITE_ANY_PATH=true."
        )

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

    if not require_approval:
        allowed, reason = can_auto_execute(action.action_type, action.payload)
        if not allowed:
            raise ActionExecutionError(f"Action non auto-executable: {reason}.")

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
        elif action.action_type == "git_initial_commit":
            result = execute_git_initial_commit(action)
        elif action.action_type == "github_repo_create":
            result = execute_github_repo_create(action)
        elif action.action_type == "git_push":
            result = execute_git_push(action)
        elif action.action_type == "linkedin_browser_prepare_post":
            result = execute_linkedin_browser_prepare_post(action)
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
