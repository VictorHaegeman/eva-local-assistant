from typing import Any


SAFE_ACTION_TYPES = {
    "codex_prompt",
    "project_context",
    "project_prompt",
    "web_search",
}

CRITICAL_ACTION_TYPES = {
    "command",
    "delete_path",
    "send_message",
    "write_file",
}

CRITICAL_COMMAND_MARKERS = (
    "git push",
    "git reset",
    "git clean",
    "git checkout --",
    "gh pr create",
    "gh pr merge",
    "remove-item",
    "del ",
    "erase ",
    "rmdir",
    "rd ",
    "shutdown",
    "format",
    "publish",
)


def requires_confirmation(action_type: str, payload: dict[str, Any] | None = None) -> bool:
    clean_type = action_type.strip().lower()

    if clean_type in SAFE_ACTION_TYPES:
        return False

    if clean_type in CRITICAL_ACTION_TYPES:
        return True

    if clean_type == "read_file":
        return False

    if clean_type == "command":
        return True

    payload = payload or {}
    command = str(payload.get("command", "")).strip().lower()
    if command and any(marker in command for marker in CRITICAL_COMMAND_MARKERS):
        return True

    return True


def autonomy_policy_text() -> str:
    return (
        "Politique d'autonomie Eva:\n"
        "- Eva peut faire directement les actions de lecture, analyse, recherche web gratuite, "
        "resume, lecture Gmail configuree, brouillon email sans envoi, creation de taches "
        "locales et preparation de prompts Cursor/Codex.\n"
        "- Eva doit demander validation avant toute action critique: commande systeme, ecriture "
        "ou suppression de fichier, git push, publication, envoi de message/email, utilisation "
        "active d'un compte externe ou action irreversible.\n"
        "- Eva ne doit jamais pretendre avoir modifie, envoye, publie ou pousse quelque chose "
        "si l'action n'a pas vraiment ete executee."
    )
