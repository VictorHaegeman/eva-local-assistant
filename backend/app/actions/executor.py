import shutil
import subprocess
from pathlib import Path

from app.actions.action_store import EvaAction, update_action_status
from app.config import settings


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


def execute_action(action_id: int) -> dict[str, object]:
    from app.actions.action_store import action_to_dict, get_action

    if not settings.eva_system_actions_enabled:
        raise ActionExecutionError("Les actions systeme Eva sont desactivees dans .env.")

    action = get_action(action_id)

    if action.status != "approved":
        raise ActionExecutionError("Action non approuvee.")

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
