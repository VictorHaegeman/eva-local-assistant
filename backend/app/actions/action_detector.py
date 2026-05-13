import re

from app.actions.action_store import EvaAction, create_action


COMMAND_PATTERNS = (
    r"^\s*(?:eva[, ]*)?(?:lance|execute|exécute|run)\s+(?:la\s+)?commande\s+[`\"']?(?P<command>.+?)[`\"']?\s*$",
    r"^\s*(?:eva[, ]*)?(?:lance|execute|exécute|run)\s+[`\"'](?P<command>.+?)[`\"']\s*$",
)

CODEX_MARKERS = ("codex", "cursor")

PATH_PATTERN = r"(?P<path>[A-Za-z]:\\[^`\"'\n]+|/[^\s`\"'\n]+)"


def _clean_value(value: str) -> str:
    return value.strip().strip("`\"'")


def create_pending_action_from_message(message: str) -> EvaAction | None:
    for pattern in COMMAND_PATTERNS:
        match = re.match(pattern, message, flags=re.IGNORECASE | re.DOTALL)
        if match:
            command = _clean_value(match.group("command"))
            return create_action(
                action_type="command",
                title="Executer une commande locale",
                description="Action creee depuis le chat. Elle necessite validation avant execution.",
                payload={"command": command},
            )

    normalized = message.lower()
    if any(marker in normalized for marker in CODEX_MARKERS) and (
        "prompt" in normalized or "prepare" in normalized or "prépare" in normalized
    ):
        return create_action(
            action_type="codex_prompt",
            title="Preparer un prompt Cursor/Codex",
            description="Eva prepare un prompt, sans appeler Codex ni API OpenAI.",
            payload={"prompt": message},
        )

    read_match = re.search(
        rf"(?:lis|lire|ouvre|affiche).{{0,30}}{PATH_PATTERN}",
        message,
        flags=re.IGNORECASE,
    )
    if read_match:
        return create_action(
            action_type="read_file",
            title="Lire un fichier local hors racines autorisees",
            description="Lecture large demandee depuis le chat. Validation requise.",
            payload={"path": _clean_value(read_match.group("path"))},
        )

    delete_match = re.search(
        rf"(?:supprime|efface|delete).{{0,30}}{PATH_PATTERN}",
        message,
        flags=re.IGNORECASE,
    )
    if delete_match:
        return create_action(
            action_type="delete_path",
            title="Supprimer un chemin local",
            description="Suppression demandee depuis le chat. Validation requise.",
            payload={"path": _clean_value(delete_match.group("path")), "recursive": False},
        )

    return None
