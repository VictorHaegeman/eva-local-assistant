from app.cognition.tool_result import ToolResult


def fallback_for_result(result: ToolResult) -> tuple[str, ...]:
    if result.tool == "cursor_bridge":
        return (
            "ecrire un prompt Cursor dans le projet",
            "copier le prompt dans le presse-papiers",
            "notifier Victor que cursor-agent n'est pas disponible si c'est le cas",
        )
    if result.tool == "browser_assistant":
        return (
            "ouvrir une recherche web simple dans Brave",
            "retourner une URL exploitable dans le chat",
        )
    if result.tool == "gmail_client":
        return (
            "verifier le token Gmail local",
            "lancer le flux OAuth local si le token est absent",
            "ne jamais inventer de mail",
        )
    if result.tool == "screen_reader":
        return (
            "prendre une nouvelle capture",
            "reduire la demande a une action visuelle simple",
        )
    return ()
