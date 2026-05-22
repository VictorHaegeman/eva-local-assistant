import json
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.files.local_files import BLOCKED_NAMES, _has_blocked_part, _is_readable_file


class ProjectStoreError(Exception):
    """Raised when Eva cannot safely inspect a configured project."""


@dataclass(frozen=True)
class ProjectResolution:
    project: dict[str, Any]
    confidence: float
    reason: str
    exact: bool = False


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
PROJECTS_PATH = DATA_DIR / "eva_projects.json"
PROJECTS_EXAMPLE_PATH = DATA_DIR / "eva_projects.example.json"
MAX_TREE_ITEMS = 500
MAX_PROJECT_FILE_BYTES = 350_000


def ensure_projects_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if PROJECTS_PATH.exists():
        return

    if PROJECTS_EXAMPLE_PATH.exists():
        shutil.copyfile(PROJECTS_EXAMPLE_PATH, PROJECTS_PATH)
    else:
        PROJECTS_PATH.write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "name": "Eva",
                            "path": ".",
                            "description": "Assistant local",
                            "type": "code",
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _resolve_project_path(path_value: str) -> Path:
    raw_path = Path(path_value).expanduser()
    if not raw_path.is_absolute():
        raw_path = PROJECT_ROOT / raw_path
    return raw_path.resolve()


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(without_accents.split())


def _tokens(value: str) -> set[str]:
    stopwords = {
        "sur",
        "pour",
        "avec",
        "dans",
        "projet",
        "repo",
        "code",
        "bosser",
        "travaille",
        "travailler",
        "ouvre",
        "ouvrir",
        "cursor",
        "codex",
        "eva",
        "veux",
        "je",
        "tu",
        "et",
        "en",
        "ou",
        "au",
        "aux",
        "ce",
        "cet",
        "cette",
        "sur",
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "de",
        "du",
    }
    normalized = _normalize_text(value)
    split_normalized = re.sub(r"[-_/\\.]+", " ", normalized)
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]{2,}", split_normalized)
        if token not in stopwords
    }
    tokens.update(
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", normalized)
        if token not in stopwords and ("-" in token or "_" in token)
    )

    if "machine" in tokens and any(token in tokens for token in {"learning", "leurning", "ml"}):
        tokens.update({"neural", "network", "ai", "ml"})
    if "ia" in tokens:
        tokens.update({"ai", "neural", "ml"})

    return tokens


def load_projects() -> list[dict[str, Any]]:
    ensure_projects_file()

    try:
        payload = json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectStoreError("data/eva_projects.json contient du JSON invalide.") from exc
    except OSError as exc:
        raise ProjectStoreError("Impossible de lire data/eva_projects.json.") from exc

    projects = payload.get("projects", [])
    if not isinstance(projects, list):
        raise ProjectStoreError("projects doit etre une liste.")

    loaded_projects: list[dict[str, Any]] = []
    for project in projects:
        if not isinstance(project, dict):
            continue

        name = str(project.get("name", "")).strip()
        path_value = str(project.get("path", "")).strip()
        description = str(project.get("description", "")).strip()
        project_type = str(project.get("type", "code")).strip()
        aliases_payload = project.get("aliases", [])
        aliases = (
            [str(alias).strip() for alias in aliases_payload if str(alias).strip()]
            if isinstance(aliases_payload, list)
            else []
        )

        if not name or not path_value:
            continue

        resolved_path = _resolve_project_path(path_value)
        if resolved_path.exists() and resolved_path.is_dir():
            loaded_projects.append(
                {
                    "name": name,
                    "path": str(resolved_path),
                    "description": description,
                    "type": project_type,
                    "aliases": aliases,
                }
            )

    if not loaded_projects:
        raise ProjectStoreError("Aucun projet valide n'est configure.")

    return loaded_projects


def get_project(project_name: str) -> dict[str, Any]:
    for project in load_projects():
        if project["name"].lower() == project_name.lower():
            return project

    resolution = resolve_project_reference(project_name, minimum_confidence=0.34)
    if resolution:
        return resolution.project

    raise ProjectStoreError(f"Projet introuvable: {project_name}")


def _project_haystack(project: dict[str, Any]) -> str:
    aliases = project.get("aliases", [])
    alias_text = " ".join(str(alias) for alias in aliases if str(alias).strip()) if isinstance(aliases, list) else ""
    return " ".join(
        [
            str(project.get("name", "")),
            alias_text,
            str(project.get("description", "")),
            Path(str(project.get("path", ""))).name,
            str(project.get("path", "")),
            str(project.get("type", "")),
        ]
    )


def resolve_project_reference(reference: str, minimum_confidence: float = 0.22) -> ProjectResolution | None:
    projects = load_projects()
    normalized_reference = _normalize_text(reference)
    reference_tokens = _tokens(reference)

    exact_alias_hits: list[ProjectResolution] = []
    for project in projects:
        names = [str(project["name"])]
        aliases = project.get("aliases", [])
        if isinstance(aliases, list):
            names.extend(str(alias) for alias in aliases)

        for name in names:
            normalized_name = _normalize_text(name)
            if normalized_name and (
                normalized_name == normalized_reference
                or normalized_name in normalized_reference
            ):
                exact_alias_hits.append(
                    ProjectResolution(
                        project=project,
                        confidence=0.98,
                        reason=f"nom ou alias detecte: {name}",
                        exact=True,
                    )
                )
                break

    if exact_alias_hits:
        return exact_alias_hits[0]

    scored: list[ProjectResolution] = []
    for project in projects:
        haystack = _project_haystack(project)
        haystack_normalized = _normalize_text(haystack)
        haystack_tokens = _tokens(haystack)
        if not haystack_tokens:
            continue

        token_hits = reference_tokens & haystack_tokens
        score = len(token_hits) / max(len(reference_tokens), 1)
        name_tokens = _tokens(str(project.get("name", "")))
        alias_tokens = _tokens(" ".join(str(alias) for alias in project.get("aliases", []))) if isinstance(project.get("aliases", []), list) else set()
        description_tokens = _tokens(str(project.get("description", "")))

        if token_hits & name_tokens:
            score += 0.25
        if token_hits & alias_tokens:
            score += 0.25
        if token_hits & description_tokens:
            score += 0.12

        path_name = _normalize_text(Path(str(project.get("path", ""))).name)
        if path_name and path_name in normalized_reference:
            score += 0.2

        if not token_hits and normalized_reference not in haystack_normalized:
            continue

        reason = (
            f"mots communs: {', '.join(sorted(token_hits))}"
            if token_hits
            else "similarite avec le chemin ou la description"
        )
        scored.append(
            ProjectResolution(
                project=project,
                confidence=min(score, 0.95),
                reason=reason,
                exact=False,
            )
        )

    if not scored:
        return None

    best = sorted(scored, key=lambda item: item.confidence, reverse=True)[0]
    if best.confidence < minimum_confidence:
        return None
    return best


def resolve_project_name(reference: str, minimum_confidence: float = 0.22) -> str | None:
    resolution = resolve_project_reference(reference, minimum_confidence=minimum_confidence)
    if not resolution:
        return None
    return str(resolution.project["name"])


def _resolve_project_file(project: dict[str, str], relative_path: str) -> Path:
    root = Path(project["path"]).resolve()
    candidate = (root / relative_path).resolve()

    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ProjectStoreError("Chemin refuse: il sort du projet.") from exc

    if _has_blocked_part(relative):
        raise ProjectStoreError("Chemin refuse: dossier ou fichier sensible bloque.")

    if not candidate.exists():
        raise ProjectStoreError("Fichier introuvable dans le projet.")

    return candidate


def project_tree(project_name: str, limit: int = MAX_TREE_ITEMS) -> dict[str, Any]:
    project = get_project(project_name)
    root = Path(project["path"]).resolve()
    safe_limit = min(max(limit, 1), MAX_TREE_ITEMS)
    items: list[dict[str, Any]] = []

    for path in root.rglob("*"):
        if len(items) >= safe_limit:
            break

        relative = path.relative_to(root)
        if _has_blocked_part(relative) or any(part.startswith(".") for part in relative.parts):
            continue

        items.append(
            {
                "path": relative.as_posix(),
                "type": "directory" if path.is_dir() else "file",
                "readable": _is_readable_file(path),
            }
        )

    return {
        "project": project,
        "items": items,
    }


def read_project_file(project_name: str, relative_path: str) -> dict[str, Any]:
    project = get_project(project_name)
    file_path = _resolve_project_file(project, relative_path)

    if not _is_readable_file(file_path):
        raise ProjectStoreError("Fichier refuse ou type non lisible.")

    size = file_path.stat().st_size
    if size > MAX_PROJECT_FILE_BYTES:
        raise ProjectStoreError("Fichier trop volumineux pour cette version.")

    content = file_path.read_bytes().decode("utf-8", errors="replace")
    return {
        "project": project["name"],
        "path": file_path.relative_to(Path(project["path"])).as_posix(),
        "content": content,
        "size": size,
    }


def build_cursor_prompt(project_name: str, task: str) -> str:
    project = get_project(project_name)
    tree = project_tree(project_name, limit=120)
    file_list = "\n".join(f"- {item['path']}" for item in tree["items"][:120])

    return f"""
Tu es dans le projet {project['name']}.
Chemin local: {project['path']}
Description: {project.get('description', '')}

Objectif:
{task.strip()}

Contexte du repo:
{file_list}

Instructions pour Cursor/Codex:
- Lis d'abord les fichiers pertinents.
- Ne modifie pas de fichiers sans comprendre les patterns existants.
- Garde les changements scopes.
- Ajoute ou adapte les tests si le changement touche du comportement.
- Explique les fichiers modifies et les verifications a faire.
""".strip()


def build_branch_plan(project_name: str, branch_name: str) -> dict[str, Any]:
    project = get_project(project_name)
    safe_branch = branch_name.strip().replace(" ", "-")

    if not safe_branch:
        raise ProjectStoreError("Nom de branche vide.")

    return {
        "project": project,
        "warning": "Eva ne lance pas ces commandes. Copie-les seulement apres validation.",
        "commands": [
            f"cd /d \"{project['path']}\"",
            "git status",
            f"git switch -c {safe_branch}",
        ],
    }
