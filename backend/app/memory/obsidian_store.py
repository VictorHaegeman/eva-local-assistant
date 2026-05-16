import re
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings


class ObsidianMemoryError(Exception):
    """Raised when Eva cannot read or write the local Obsidian memory vault."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FOLDERS = (
    "00 - Eva",
    "10 - Profile",
    "20 - Memories",
    "30 - Projects",
    "40 - Daily",
)


def _vault_path() -> Path:
    configured = Path(settings.eva_obsidian_vault_path)
    if configured.is_absolute():
        return configured
    return PROJECT_ROOT / configured


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


def ensure_obsidian_vault() -> Path:
    vault = _vault_path()
    if not settings.eva_obsidian_memory_enabled:
        return vault

    try:
        vault.mkdir(parents=True, exist_ok=True)
        for folder in DEFAULT_FOLDERS:
            (vault / folder).mkdir(parents=True, exist_ok=True)

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
                        "- les actions reelles restent soumises a validation humaine.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
    except OSError as exc:
        raise ObsidianMemoryError("Impossible d'initialiser le vault Obsidian local.") from exc

    return vault


def obsidian_status() -> dict[str, Any]:
    vault = _vault_path()
    markdown_files = list(vault.rglob("*.md")) if vault.exists() else []
    return {
        "enabled": settings.eva_obsidian_memory_enabled,
        "path": str(vault),
        "exists": vault.exists(),
        "markdown_files": len(markdown_files),
        "folders": [
            {
                "name": folder,
                "exists": (vault / folder).exists(),
            }
            for folder in DEFAULT_FOLDERS
        ],
        "git_ignored": True,
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
