from app.integrations.cursor_bridge import CursorBridgeError, prepare_cursor_work_session
from app.projects.project_store import ProjectStoreError, build_cursor_prompt, load_projects, project_tree


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


def infer_project_name(message: str) -> str | None:
    normalized = _normalize(message)
    projects = load_projects()

    for project in projects:
        project_name = str(project["name"])
        if _normalize(project_name) in normalized:
            return project_name

    if len(projects) == 1:
        return str(projects[0]["name"])

    if "eva" in normalized or "ce projet" in normalized or "repo actuel" in normalized:
        for project in projects:
            if _normalize(str(project["name"])) == "eva":
                return str(project["name"])

    return None


def build_chat_cursor_prompt_response(message: str) -> str:
    projects = load_projects()
    project_name = infer_project_name(message)

    if not project_name:
        project_list = "\n".join(f"- {project['name']}" for project in projects)
        return (
            "Je peux preparer le prompt Cursor, mais il me manque le projet cible.\n\n"
            f"Projets connus:\n{project_list}\n\n"
            "Renvoie ta demande avec le nom du projet."
        )

    prompt = build_cursor_prompt(project_name, message)
    tree = project_tree(project_name, limit=20)
    preview = "\n".join(f"- {item['path']}" for item in tree["items"][:20])

    return (
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
    project_name = infer_project_name(message)

    if not project_name:
        project_list = "\n".join(f"- {project['name']}" for project in projects)
        return (
            "Je peux ouvrir Cursor et preparer le prompt, mais il me manque le projet cible.\n\n"
            f"Projets connus:\n{project_list}\n\n"
            "Renvoie par exemple: ouvre le projet Eva dans Cursor et prepare un prompt Codex pour ..."
        )

    try:
        session = prepare_cursor_work_session(project_name, message)
    except CursorBridgeError as exc:
        raise ProjectStoreError(str(exc)) from exc

    project = session["project"]
    lines = [
        f"Session Cursor preparee pour {project['name']}.",
        f"Projet: {project['path']}",
    ]

    if session["prompt_file"]:
        lines.append(f"Fichier prompt ecrit: {session['prompt_file']}")
    if session["copied_to_clipboard"]:
        lines.append("Prompt copie dans le presse-papiers Windows.")
    if session["cursor_opened"]:
        lines.append("Cursor ouvert sur le projet.")

    lines.extend(
        [
            "",
            "Limite actuelle: Eva ne controle pas le panneau Codex/Cursor via une API officielle.",
            "Le prompt est pret: ouvre le chat/agent Cursor et colle avec Ctrl+V.",
        ]
    )
    return "\n".join(lines)


def build_project_context_for_chat(message: str) -> str | None:
    project_name = infer_project_name(message)
    if not project_name:
        return None

    tree = project_tree(project_name, limit=100)
    project = tree["project"]
    file_list = "\n".join(f"- {item['path']}" for item in tree["items"][:100])

    return (
        f"Projet local detecte: {project['name']}\n"
        f"Chemin: {project['path']}\n"
        f"Description: {project.get('description', '')}\n\n"
        f"Structure partielle:\n{file_list}"
    )
