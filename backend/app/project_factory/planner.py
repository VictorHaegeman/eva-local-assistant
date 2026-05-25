import re
import unicodedata
from pathlib import Path
from typing import Any

from app.actions.action_store import create_action
from app.config import settings
from app.integrations.stitch_design import stitch_prompt_file_content


class ProjectFactoryError(Exception):
    """Raised when Eva cannot prepare a project factory plan."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _safe_project_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9 _-]+", "", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return "Nouveau Projet"
    return cleaned[:60]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower()).strip("-")
    return slug or "nouveau-projet"


def _normalize_project_text(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def infer_project_name(idea: str) -> str:
    normalized_idea = _normalize_project_text(idea)
    patterns = (
        r"(?:idee|idée|idÃ©e)\s+de\s+projet\s*:\s*(?P<name>[A-Za-z0-9 _-]{3,60})",
        r"(?:nomme|nommé|appelle|appelé|projet)\s+(?P<name>[A-Za-z0-9 _-]{3,60})",
        r"(?:idee|idée|projet)\s*:\s*(?P<name>[A-Za-z0-9 _-]{3,60})",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized_idea, flags=re.IGNORECASE)
        if match:
            return _safe_project_name(match.group("name"))

    words = re.findall(r"[A-Za-z0-9]+", normalized_idea)
    if not words:
        return "Nouveau Projet"
    ignored = {
        "eva",
        "cree",
        "crée",
        "faire",
        "nouveau",
        "nouvelle",
        "projet",
        "idee",
        "idée",
        "j",
        "ai",
        "jai",
        "de",
        "du",
        "des",
        "pour",
        "sur",
        "mon",
        "ma",
        "mes",
        "ton",
        "ta",
        "tes",
        "lance",
        "demarre",
        "prepare",
        "idée",
        "une",
        "un",
        "app",
        "application",
        "site",
        "web",
    }
    useful = [word for word in words if word.lower() not in ignored]
    return _safe_project_name(" ".join(useful[:4]) or "Nouveau Projet")


def infer_stack(idea: str) -> dict[str, str]:
    normalized = idea.lower()
    if "fastapi" in normalized or "backend" in normalized:
        return {
            "template": "react-vite-fastapi",
            "frontend": "React + Vite",
            "backend": "Python FastAPI",
            "notes": "Bon choix pour une app web locale ou SaaS.",
        }
    if "python" in normalized or "script" in normalized or "automation" in normalized:
        return {
            "template": "python-cli",
            "frontend": "none",
            "backend": "Python",
            "notes": "Bon choix pour un outil local ou une automation.",
        }
    if "landing" in normalized or "site" in normalized:
        return {
            "template": "landing-page",
            "frontend": "React + Vite",
            "backend": "none",
            "notes": "Bon choix pour une vitrine rapide.",
        }
    return {
        "template": "saas-mvp",
        "frontend": "React + Vite",
        "backend": "Python FastAPI",
        "notes": "Template par defaut pour prototype produit.",
    }


def _workspace_base() -> Path:
    configured = Path(settings.eva_projects_dir).expanduser()
    if configured.is_absolute():
        return configured.resolve()
    return (PROJECT_ROOT / configured).resolve()


def _cursor_prompt(project_name: str, idea: str, stack: dict[str, str], workspace_path: Path) -> str:
    return f"""
Tu es Cursor dans le projet {project_name}.

Chemin local cible:
{workspace_path}

Idee de Victor:
{idea.strip()}

Stack proposee:
- template: {stack['template']}
- frontend: {stack['frontend']}
- backend: {stack['backend']}
- notes: {stack['notes']}

Objectif:
Construire une V1 propre, simple et maintenable.

Instructions:
1. Lis d'abord PROJECT_BRIEF.md, TASKS.md et README.md.
2. Si STITCH_DESIGN_PROMPT.md existe, utilise-le pour demander une maquette Google Stitch ou pour aligner le design.
3. Propose une architecture minimale.
4. Commence par le squelette du projet.
5. Garde les changements scopes.
6. N'ajoute pas d'API payante.
7. Documente les commandes de lancement.
8. Code la V1 directement dans ce workspace si cursor-agent est disponible.
9. Ne publie rien et n'envoie aucun message externe. Eva gere Git/GitHub selon sa configuration locale.

Livrable attendu:
- code initial;
- README clair;
- checklist de verification;
- prochaines etapes.
""".strip()


def build_project_plan(idea: str, project_name: str | None = None) -> dict[str, Any]:
    clean_idea = idea.strip()
    if len(clean_idea) < 8:
        raise ProjectFactoryError("Idee projet trop courte.")

    name = _safe_project_name(project_name or infer_project_name(clean_idea))
    slug = _slugify(name)
    stack = infer_stack(clean_idea)
    workspace_path = _workspace_base() / slug
    cursor_prompt = _cursor_prompt(name, clean_idea, stack, workspace_path)
    repo_name = slug

    files = {
        "README.md": f"# {name}\n\nProjet prepare par Eva.\n\n## Idee\n\n{clean_idea}\n\n## Stack\n\n- Frontend: {stack['frontend']}\n- Backend: {stack['backend']}\n\n## Lancement\n\nA completer apres generation du projet.\n",
        "PROJECT_BRIEF.md": f"# Brief projet - {name}\n\n## Idee\n\n{clean_idea}\n\n## Objectif V1\n\nConstruire une premiere version utilisable, simple et maintenable.\n\n## Stack proposee\n\n- Template: {stack['template']}\n- Frontend: {stack['frontend']}\n- Backend: {stack['backend']}\n- Notes: {stack['notes']}\n\n## Contraintes\n\n- Local-first quand possible.\n- Pas d'API payante obligatoire.\n- Secrets hors Git.\n- GitHub et push geres par Eva Project Factory si les flags locaux sont actifs.\n",
        "TASKS.md": f"# Tasks - {name}\n\n- [ ] Valider le scope V1\n- [ ] Creer le squelette technique\n- [ ] Ajouter README de lancement\n- [ ] Verifier le rendu local\n- [ ] Preparer le premier commit\n",
        "CURSOR_PROMPT.md": cursor_prompt + "\n",
        ".gitignore": "node_modules/\ndist/\nbuild/\n.env\n.env.*\n!.env.example\n.venv/\n__pycache__/\n*.pyc\n.DS_Store\nThumbs.db\n",
    }
    if stack["frontend"] != "none":
        files["STITCH_DESIGN_PROMPT.md"] = stitch_prompt_file_content(
            request=clean_idea,
            project_name=name,
        )

    commands = {
        "open_cursor": f'cursor "{workspace_path}"',
        "github_create_repo": f'gh repo create {repo_name} --private --source "{workspace_path}" --remote origin',
        "git_initial_commit": f'cd /d "{workspace_path}" && git init && git add . && git commit -m "Initial project scaffold"',
        "git_push": f'cd /d "{workspace_path}" && git push -u origin main',
        "cursor_agent_run": "cursor-agent -p <CURSOR_PROMPT.md>",
    }

    return {
        "project_name": name,
        "slug": slug,
        "workspace_path": str(workspace_path),
        "repo_name": repo_name,
        "stack": stack,
        "idea": clean_idea,
        "files": files,
        "commands": commands,
        "cursor_prompt": cursor_prompt,
        "safety": {
            "auto_scope": [
                "creer le dossier projet",
                "ecrire les fichiers",
                "copier dans le presse-papiers",
                "ouvrir Cursor",
                "lancer cursor-agent pour coder la V1",
                "creer le repo GitHub",
                "git push si EVA_PROJECT_FACTORY_AUTO_PUSH=true",
            ],
            "protected": [
                "appel API OpenAI",
                "automatisation ChatGPT web",
                "envoi ou publication sans validation",
                "suppression de fichiers",
            ],
        },
    }


def create_project_factory_action(idea: str, project_name: str | None = None) -> dict[str, Any]:
    plan = build_project_plan(idea=idea, project_name=project_name)
    action = create_action(
        action_type="project_workspace_create",
        title=f"Creer le workspace projet {plan['project_name']}",
        description=(
            "Project Factory: cree le dossier, les fichiers de cadrage, "
            "CURSOR_PROMPT.md et prepare les commandes locales."
        ),
        payload=plan,
    )
    return {
        "plan": plan,
        "action": action,
    }


def create_project_factory_actions(idea: str, project_name: str | None = None) -> dict[str, Any]:
    bundle = create_project_factory_action(idea=idea, project_name=project_name)
    plan = bundle["plan"]
    workspace_action = bundle["action"]
    clipboard_action = create_action(
        action_type="clipboard_set_prompt",
        title=f"Copier le prompt Cursor pour {plan['project_name']}",
        description="Copie le prompt dans le presse-papiers Windows.",
        payload={"prompt": plan["cursor_prompt"], "project_name": plan["project_name"]},
    )
    cursor_action = create_action(
        action_type="cursor_open_project",
        title=f"Ouvrir Cursor pour {plan['project_name']}",
        description="Ouvre Cursor sur le dossier projet.",
        payload={"workspace_path": plan["workspace_path"]},
    )
    cursor_agent_action = create_action(
        action_type="cursor_agent_project_run",
        title=f"Lancer cursor-agent pour coder {plan['project_name']}",
        description=(
            "Lance cursor-agent en arriere-plan, surveille le log, audite le resultat "
            "et relance une correction si l'audit echoue."
        ),
        payload={
            "workspace_path": plan["workspace_path"],
            "project_name": plan["project_name"],
            "repo_name": plan["repo_name"],
            "idea": plan["idea"],
            "cursor_prompt": plan["cursor_prompt"],
        },
    )
    github_action = create_action(
        action_type="github_repo_create",
        title=f"Creer le repo GitHub {plan['repo_name']}",
        description="Cree le repo via GitHub CLI gh si gh est authentifie.",
        payload={
            "workspace_path": plan["workspace_path"],
            "repo_name": plan["repo_name"],
            "visibility": "private",
        },
    )
    commit_action = create_action(
        action_type="git_initial_commit",
        title=f"Commit initial pour {plan['project_name']}",
        description="Cree un commit local initial dans le workspace projet.",
        payload={
            "workspace_path": plan["workspace_path"],
            "commit_message": "Initial project scaffold",
        },
    )
    push_action = create_action(
        action_type="git_push",
        title=f"Pousser {plan['project_name']} sur GitHub",
        description="Pousse la branche locale vers origin via Git.",
        payload={"workspace_path": plan["workspace_path"]},
    )

    return {
        "plan": plan,
        "actions": [
            workspace_action,
            clipboard_action,
            cursor_action,
            commit_action,
            github_action,
            cursor_agent_action,
            push_action,
        ],
    }
