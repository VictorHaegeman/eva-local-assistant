from app.integrations.cursor_bridge import CursorBridgeError, prepare_cursor_work_session
from app.projects.project_store import (
    ProjectResolution,
    ProjectStoreError,
    build_cursor_prompt,
    load_projects,
    project_tree,
    resolve_project_reference,
)


CURSOR_MARKERS = ("cursor", "codex")
PROMPT_MARKERS = (
    "prompt",
    "bosse",
    "bosser",
    "travaille",
    "travailler",
    "corrige",
    "amelior",
    "ouvre",
    "ouvrir",
    "lance",
    "envoie",
    "envoyer",
)


def _normalize(value: str) -> str:
    return value.lower().replace("é", "e").replace("è", "e").replace("ê", "e")


def detect_cursor_prompt_request(message: str) -> bool:
    normalized = _normalize(message)
    return any(marker in normalized for marker in CURSOR_MARKERS) and any(
        marker in normalized for marker in PROMPT_MARKERS
    )


def infer_project_resolution(message: str) -> ProjectResolution | None:
    normalized = _normalize(message)
    projects = load_projects()

    for project in projects:
        project_name = str(project["name"])
        if _normalize(project_name) in normalized:
            return ProjectResolution(
                project=project,
                confidence=0.98,
                reason=f"nom detecte: {project_name}",
                exact=True,
            )

    if len(projects) == 1:
        return ProjectResolution(
            project=projects[0],
            confidence=0.72,
            reason="un seul projet configure",
            exact=False,
        )

    if "eva" in normalized or "ce projet" in normalized or "repo actuel" in normalized:
        for project in projects:
            if _normalize(str(project["name"])) == "eva":
                return ProjectResolution(
                    project=project,
                    confidence=0.9,
                    reason="reference au repo Eva actuel",
                    exact=False,
                )

    return resolve_project_reference(message)


def infer_project_name(message: str) -> str | None:
    resolution = infer_project_resolution(message)
    return str(resolution.project["name"]) if resolution else None


def _resolution_intro(resolution: ProjectResolution) -> str:
    project_name = str(resolution.project["name"])
    if resolution.exact:
        return f"Projet detecte: {project_name}."
    return (
        f"Je suppose que tu parles de {project_name} "
        f"({round(resolution.confidence * 100)}%, {resolution.reason})."
    )


def build_chat_cursor_prompt_response(message: str) -> str:
    projects = load_projects()
    resolution = infer_project_resolution(message)

    if not resolution:
        project_list = "\n".join(f"- {project['name']}" for project in projects)
        return (
            "Je peux preparer le prompt Cursor, mais il me manque le projet cible.\n\n"
            f"Projets connus:\n{project_list}\n\n"
            "Renvoie ta demande avec le nom du projet."
        )

    project_name = str(resolution.project["name"])
    prompt = build_cursor_prompt(project_name, message)
    tree = project_tree(project_name, limit=20)
    preview = "\n".join(f"- {item['path']}" for item in tree["items"][:20])

    return (
        f"{_resolution_intro(resolution)}\n"
        f"Oui. Je peux lire le projet {project_name} et preparer un prompt de travail pour Cursor.\n"
        "Je ne l'envoie pas a l'API OpenAI et je ne controle pas Cursor directement.\n\n"
        "Prompt pret a coller dans Cursor:\n\n"
        "```text\n"
        f"{prompt}\n"
        "```\n\n"
        f"Contexte inspecte automatiquement:\n{preview}"
    )


def build_cursor_work_session_response(message: str) -> str:
    projects = load_projects()
    resolution = infer_project_resolution(message)

    if not resolution:
        project_list = "\n".join(f"- {project['name']}" for project in projects)
        return (
            "Je peux ouvrir Cursor et preparer le prompt, mais il me manque le projet cible.\n\n"
            f"Projets connus:\n{project_list}\n\n"
            "Renvoie par exemple: ouvre le projet Eva dans Cursor et prepare un prompt Codex pour ..."
        )

    project_name = str(resolution.project["name"])
    try:
        session = prepare_cursor_work_session(project_name, message)
    except CursorBridgeError as exc:
        raise ProjectStoreError(str(exc)) from exc

    project = session["project"]
    lines = [
        _resolution_intro(resolution),
        f"Session Cursor preparee pour {project['name']}.",
        f"Projet: {project['path']}",
    ]

    if session["prompt_file"]:
        lines.append(f"Fichier prompt ecrit: {session['prompt_file']}")
    if session["copied_to_clipboard"]:
        lines.append("Prompt copie dans le presse-papiers Windows.")
    if session["cursor_opened"]:
        lines.append("Cursor ouvert sur le projet.")

    agent = session.get("cursor_agent", {})
    if isinstance(agent, dict):
        if agent.get("started"):
            lines.append(f"cursor-agent lance en arriere-plan. Log: {agent.get('log_path')}")
        elif agent.get("available") is False:
            lines.append("cursor-agent introuvable: installe/active Cursor CLI Agent pour execution autonome.")

    lines.extend(
        [
            "",
            "Fallback GUI: si cursor-agent n'est pas disponible, le prompt est pret dans le presse-papiers et le fichier EVA_CURSOR_PROMPT.md.",
        ]
    )
    return "\n".join(lines)


def build_project_context_for_chat(message: str) -> str | None:
    resolution = infer_project_resolution(message)
    if not resolution:
        return None

    project_name = str(resolution.project["name"])
    tree = project_tree(project_name, limit=100)
    project = tree["project"]
    file_list = "\n".join(f"- {item['path']}" for item in tree["items"][:100])

    return (
        f"{_resolution_intro(resolution)}\n"
        f"Projet local detecte: {project['name']}\n"
        f"Chemin: {project['path']}\n"
        f"Description: {project.get('description', '')}\n\n"
        f"Structure partielle:\n{file_list}"
    )
