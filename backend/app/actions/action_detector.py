import re

from app.actions.action_store import EvaAction, create_action


COMMAND_PATTERNS = (
    r"^\s*(?:eva[, ]*)?(?:lance|execute|exécute|run)\s+(?:la\s+)?commande\s+[`\"']?(?P<command>.+?)[`\"']?\s*$",
    r"^\s*(?:eva[, ]*)?(?:lance|execute|exécute|run)\s+[`\"'](?P<command>.+?)[`\"']\s*$",
)

PATH_PATTERN = r"(?P<path>[A-Za-z]:\\[^`\"'\n]+|/[^\s`\"'\n]+)"
WRITE_PATTERNS = (
    r"(?:cree|crée|ecris|écris|modifie|write).{0,30}(?:fichier|file)\s+[`\"'](?P<path>[A-Za-z]:\\[^`\"'\n]+|/[^`\"'\n]+)[`\"']\s+(?:avec|contenu|:)\s*(?P<content>.+)$",
    r"(?:cree|crée|ecris|écris|modifie|write).{0,30}(?:fichier|file)\s+(?P<path>[A-Za-z]:\\[^\s`\"'\n]+|/[^\s`\"'\n]+)\s+(?:avec|contenu|:)\s*(?P<content>.+)$",
)


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
                description="Commande locale demandee depuis le chat.",
                payload={"command": command},
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
            description="Suppression demandee depuis le chat.",
            payload={"path": _clean_value(delete_match.group("path")), "recursive": False},
        )

    for pattern in WRITE_PATTERNS:
        match = re.search(pattern, message, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return create_action(
                action_type="write_file",
                title="Ecrire un fichier local",
                description="Ecriture fichier demandee depuis le chat.",
                payload={
                    "path": _clean_value(match.group("path")),
                    "content": _clean_value(match.group("content")),
                    "mode": "overwrite",
                },
            )

    return None
