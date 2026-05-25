import os
import json
import re
import time
import hashlib
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.config import settings
from app.memory.profile_store import ProfileStoreError, load_profile
from app.projects.project_store import ProjectStoreError, load_projects


class ObsidianMemoryError(Exception):
    """Raised when Eva cannot read or write the local Obsidian memory vault."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FOLDERS = (
    "00 - Eva",
    "10 - Profile",
    "20 - Memories",
    "30 - Projects",
    "40 - Daily",
    "50 - Operating Rules",
    "90 - Inbox",
)

VAULT_INDEX_FILE = "00 - Eva/INDEX"


def _vault_path() -> Path:
    configured = Path(settings.eva_obsidian_vault_path)
    if configured.is_absolute():
        return configured
    return PROJECT_ROOT / configured


def _obsidian_app_config_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", "")) / "obsidian"
    return Path.home() / ".config" / "obsidian"


def _obsidian_vault_id(vault: Path) -> str:
    return hashlib.sha1(str(vault.resolve()).encode("utf-8")).hexdigest()[:16]


def _obsidian_vault_name(vault: Path) -> str:
    return vault.name


def _register_obsidian_vault(vault: Path) -> dict[str, str]:
    config_dir = _obsidian_app_config_dir()
    if not str(config_dir).strip():
        return {"registered": "false", "reason": "appdata_missing"}

    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "obsidian.json"
    vault_id = _obsidian_vault_id(vault)
    now_ms = int(time.time() * 1000)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}

    vaults = payload.get("vaults")
    if not isinstance(vaults, dict):
        vaults = {}
    resolved_vault = str(vault.resolve())
    vaults = {
        key: value
        for key, value in vaults.items()
        if not (
            key != vault_id
            and isinstance(value, dict)
            and str(value.get("path", "")).lower() == resolved_vault.lower()
        )
    }
    vaults[vault_id] = {
        "path": resolved_vault,
        "ts": now_ms,
        "open": True,
    }
    payload["vaults"] = vaults
    config_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    window_state_path = config_dir / f"{vault_id}.json"
    _write_if_missing(
        window_state_path,
        json.dumps(
            {
                "x": 80,
                "y": 60,
                "width": 1280,
                "height": 850,
                "isMaximized": False,
                "devTools": False,
                "zoom": 0,
            },
            separators=(",", ":"),
        ),
    )

    return {
        "registered": "true",
        "vault_id": vault_id,
        "vault_name": _obsidian_vault_name(vault),
        "config_path": str(config_path),
    }


def _safe_filename(value: str, fallback: str = "general") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return cleaned or fallback


def _memory_to_dict(memory: Any) -> dict[str, Any]:
    if isinstance(memory, dict):
        return memory
    if is_dataclass(memory):
        return asdict(memory)
    return {
        "id": getattr(memory, "id", ""),
        "content": getattr(memory, "content", ""),
        "category": getattr(memory, "category", "general"),
        "created_at": getattr(memory, "created_at", ""),
        "source": getattr(memory, "source", "unknown"),
        "confidence": getattr(memory, "confidence", 1.0),
    }


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_generated(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _profile_markdown() -> str:
    try:
        profile = load_profile()
    except ProfileStoreError as exc:
        return f"# Profil Victor\n\nProfil indisponible: {exc}\n"

    identity = profile.get("identity", {}) if isinstance(profile, dict) else {}
    projects = profile.get("projects", []) if isinstance(profile, dict) else []
    writing = profile.get("writing_preferences", {}) if isinstance(profile, dict) else {}

    lines = [
        "# Profil Victor",
        "",
        "> Genere localement par Eva depuis `data/eva_profile.json`.",
        "",
    ]
    if isinstance(identity, dict):
        lines.append("## Identite")
        if identity.get("user_name"):
            lines.append(f"- Nom: {identity['user_name']}")
        if identity.get("email"):
            lines.append(f"- Email: {identity['email']}")
        lines.append("")

    if isinstance(projects, list) and projects:
        lines.append("## Projets")
        for project in projects:
            if not isinstance(project, dict):
                continue
            name = project.get("name", "Projet")
            lines.append(f"### {name}")
            for key in ("description", "website", "role"):
                if project.get(key):
                    lines.append(f"- {key}: {project[key]}")
            lines.append("")

    if isinstance(writing, dict) and writing:
        lines.append("## Preferences de redaction")
        if writing.get("style"):
            lines.append(f"- Style: {writing['style']}")
        if writing.get("email_signature"):
            lines.append("")
            lines.append("```text")
            lines.append(str(writing["email_signature"]))
            lines.append("```")

    return "\n".join(lines).strip() + "\n"


def _projects_markdown() -> str:
    try:
        projects = load_projects()
    except ProjectStoreError as exc:
        return f"# Projets Eva\n\nProjets indisponibles: {exc}\n"

    lines = [
        "# Projets Eva",
        "",
        "> Genere localement par Eva depuis `data/eva_projects.json`.",
        "",
    ]
    for project in projects:
        lines.append(f"## {project['name']}")
        lines.append(f"- Chemin: `{project['path']}`")
        if project.get("description"):
            lines.append(f"- Description: {project['description']}")
        if project.get("type"):
            lines.append(f"- Type: {project['type']}")
        aliases = project.get("aliases", [])
        if aliases:
            lines.append(f"- Alias: {', '.join(str(alias) for alias in aliases)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def ensure_obsidian_vault() -> Path:
    vault = _vault_path()
    if not settings.eva_obsidian_memory_enabled:
        return vault

    try:
        vault.mkdir(parents=True, exist_ok=True)
        for folder in DEFAULT_FOLDERS:
            (vault / folder).mkdir(parents=True, exist_ok=True)

        obsidian_dir = vault / ".obsidian"
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        _write_if_missing(
            obsidian_dir / "app.json",
            '{\n  "legacyEditor": false,\n  "livePreview": true\n}\n',
        )
        _write_if_missing(
            obsidian_dir / "appearance.json",
            '{\n  "theme": "obsidian",\n  "accentColor": "#54d7ff"\n}\n',
        )
        _write_if_missing(
            obsidian_dir / "graph.json",
            json.dumps(
                {
                    "collapse-filter": False,
                    "search": "",
                    "showTags": True,
                    "showAttachments": False,
                    "hideUnresolved": False,
                    "showOrphans": True,
                    "collapse-color-groups": False,
                    "colorGroups": [
                        {"query": "path:\"10 - Profile\"", "color": {"a": 1, "rgb": 5634047}},
                        {"query": "path:\"20 - Memories\"", "color": {"a": 1, "rgb": 65484}},
                        {"query": "path:\"30 - Projects\"", "color": {"a": 1, "rgb": 16755200}},
                    ],
                    "collapse-display": False,
                    "showArrow": False,
                    "textFadeMultiplier": 0,
                    "nodeSizeMultiplier": 1,
                    "lineSizeMultiplier": 1,
                    "collapse-forces": False,
                    "centerStrength": 0.518713248970312,
                    "repelStrength": 10,
                    "linkStrength": 1,
                    "linkDistance": 250,
                    "scale": 1,
                    "close": False,
                },
                indent=2,
            )
            + "\n",
        )
        _write_if_missing(
            obsidian_dir / "hotkeys.json",
            json.dumps({"graph:open": [{"modifiers": ["Mod"], "key": "G"}]}, indent=2) + "\n",
        )

        readme_path = vault / "00 - Eva" / "README.md"
        if not readme_path.exists():
            readme_path.write_text(
                "\n".join(
                    [
                        "# Eva Memory Vault",
                        "",
                        "Ce vault Obsidian est local et ignore par Git.",
                        "Eva y miroir les souvenirs non sensibles pour les rendre lisibles et editables.",
                        "",
                        "Regles:",
                        "- pas de mots de passe;",
                        "- pas de tokens API;",
                        "- pas de secrets;",
                        "- les envois, publications et suppressions restent proteges;",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

        _write_generated(
            vault / "00 - Eva" / "INDEX.md",
            "\n".join(
                [
                    "# Eva Memory Vault",
                    "",
                    "## Navigation",
                    "",
                    "- [[10 - Profile/Victor|Profil Victor]]",
                    "- [[20 - Memories/general|Souvenirs generaux]]",
                    "- [[30 - Projects/Projects|Projets]]",
                    "- [[50 - Operating Rules/Eva Operating Rules|Regles operatoires Eva]]",
                    "- [[40 - Daily|Journal quotidien]]",
                    "- Ouvre le graphe Obsidian avec `Ctrl+G` si la vue ne s'affiche pas deja.",
                    "",
                    "## Role du vault",
                    "",
                    "Ce coffre est le deuxieme cerveau lisible d'Eva: SQLite reste la source rapide, Obsidian sert a relire, corriger et enrichir les souvenirs.",
                    "",
                    "Les fichiers du coffre restent locaux et ignores par Git.",
                    "",
                ]
            ),
        )
        _write_generated(vault / "10 - Profile" / "Victor.md", _profile_markdown())
        _write_generated(vault / "30 - Projects" / "Projects.md", _projects_markdown())
        _write_if_missing(
            vault / "50 - Operating Rules" / "Eva Operating Rules.md",
            "\n".join(
                [
                    "# Eva Operating Rules",
                    "",
                    "- Comprendre l'objectif avant d'agir.",
                    "- Chercher dans la memoire et les projets avant de dire qu'une information manque.",
                    "- Ne pas inventer une action: chaque action annoncee doit avoir une preuve locale.",
                    "- Continuer avec un plan B quand une etape bloque.",
                    "- Ne jamais stocker de mot de passe, token ou secret.",
                    "- Ne jamais envoyer, publier ou supprimer sans cadre explicite et sur.",
                    "",
                ]
            ),
        )
    except OSError as exc:
        raise ObsidianMemoryError("Impossible d'initialiser le vault Obsidian local.") from exc

    return vault


def obsidian_open_uri() -> str:
    vault = _vault_path()
    return (
        "obsidian://open?"
        f"vault={quote(_obsidian_vault_name(vault))}"
        f"&file={quote(VAULT_INDEX_FILE, safe='')}"
    )


def obsidian_path_open_uri() -> str:
    index_path = _vault_path().resolve() / "00 - Eva" / "INDEX.md"
    return f"obsidian://open?path={quote(str(index_path))}"


def _open_obsidian_graph_view() -> None:
    if os.name != "nt":
        return

    script = r"""
$shell = New-Object -ComObject WScript.Shell
Start-Sleep -Seconds 3
$null = $shell.AppActivate('Obsidian')
Start-Sleep -Milliseconds 500
$shell.SendKeys('^g')
Start-Sleep -Seconds 1
$shell.SendKeys('^p')
Start-Sleep -Milliseconds 300
$shell.SendKeys('Open graph view')
Start-Sleep -Milliseconds 300
$shell.SendKeys('{ENTER}')
"""
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _obsidian_exe_path() -> Path | None:
    if os.name != "nt":
        return None

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Obsidian" / "Obsidian.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Obsidian" / "Obsidian.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Obsidian" / "Obsidian.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def obsidian_status() -> dict[str, Any]:
    vault = _vault_path()
    markdown_files = list(vault.rglob("*.md")) if vault.exists() else []
    return {
        "enabled": settings.eva_obsidian_memory_enabled,
        "path": str(vault),
        "exists": vault.exists(),
        "markdown_files": len(markdown_files),
        "open_uri": obsidian_open_uri(),
        "path_open_uri": obsidian_path_open_uri(),
        "vault_name": _obsidian_vault_name(vault),
        "vault_id": _obsidian_vault_id(vault),
        "app_config_dir": str(_obsidian_app_config_dir()),
        "folders": [
            {
                "name": folder,
                "exists": (vault / folder).exists(),
            }
            for folder in DEFAULT_FOLDERS
        ],
        "git_ignored": True,
    }


def open_obsidian_vault(open_graph: bool = True) -> dict[str, Any]:
    if not settings.eva_obsidian_memory_enabled:
        raise ObsidianMemoryError("La memoire Obsidian est desactivee.")

    vault = ensure_obsidian_vault()
    registration = _register_obsidian_vault(vault)
    uri = obsidian_open_uri()
    try:
        if os.name == "nt":
            os.startfile(uri)  # type: ignore[attr-defined]
        elif os.environ.get("XDG_CURRENT_DESKTOP"):
            subprocess.Popen(["xdg-open", uri])
        else:
            subprocess.Popen(["open", uri])
    except Exception as exc:
        raise ObsidianMemoryError(
            f"Impossible d'ouvrir Obsidian automatiquement. Ouvre ce dossier dans Obsidian: {vault}"
        ) from exc

    if open_graph:
        _open_obsidian_graph_view()

    return {
        "opened": True,
        "path": str(vault),
        "open_uri": uri,
        "registration": registration,
        "graph_requested": open_graph,
    }


def _append_to_file(path: Path, header: str, block: str) -> None:
    if not path.exists():
        path.write_text(f"{header}\n\n", encoding="utf-8")

    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{block}\n")


def _already_contains_memory(path: Path, memory_id: object) -> bool:
    if not memory_id or not path.exists():
        return False
    marker = f"| #{memory_id} |"
    return marker in path.read_text(encoding="utf-8", errors="replace")


def mirror_memory_to_obsidian(memory: Any) -> dict[str, Any]:
    if not settings.eva_obsidian_memory_enabled:
        return {"mirrored": False, "reason": "disabled"}

    vault = ensure_obsidian_vault()
    payload = _memory_to_dict(memory)
    content = str(payload.get("content", "")).strip()
    if not content:
        return {"mirrored": False, "reason": "empty"}

    category = _safe_filename(str(payload.get("category", "general")))
    memory_id = payload.get("id", "")
    source = payload.get("source", "unknown")
    confidence = payload.get("confidence", 1.0)
    created_at = payload.get("created_at") or datetime.now(UTC).isoformat()

    block = "\n".join(
        [
            f"- {created_at} | #{memory_id} | source={source} | confidence={confidence}",
            f"  - {content}",
        ]
    )

    try:
        memory_path = vault / "20 - Memories" / f"{category}.md"
        if _already_contains_memory(memory_path, memory_id):
            return {
                "mirrored": False,
                "reason": "already_present",
                "path": str(memory_path),
            }
        _append_to_file(memory_path, f"# Memories - {category}", block)

        daily_path = vault / "40 - Daily" / f"{datetime.now().date().isoformat()}.md"
        if not _already_contains_memory(daily_path, memory_id):
            _append_to_file(daily_path, f"# Journal Eva - {datetime.now().date().isoformat()}", block)
    except OSError as exc:
        raise ObsidianMemoryError("Impossible d'ecrire dans le vault Obsidian local.") from exc

    return {
        "mirrored": True,
        "path": str(memory_path),
    }


def sync_memories_to_obsidian(memories: list[Any]) -> dict[str, Any]:
    if not settings.eva_obsidian_memory_enabled:
        return {
            "synced": 0,
            "enabled": False,
            "path": str(_vault_path()),
        }

    ensure_obsidian_vault()
    synced = 0
    for memory in memories:
        result = mirror_memory_to_obsidian(memory)
        if result.get("mirrored"):
            synced += 1

    return {
        "synced": synced,
        "enabled": True,
        "path": str(_vault_path()),
    }
