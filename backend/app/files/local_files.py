import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LocalFileError(Exception):
    """Raised when Eva cannot safely access an allowed local file."""


@dataclass(frozen=True)
class AllowedRoot:
    name: str
    path: Path
    description: str = ""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
ALLOWED_PATHS_PATH = DATA_DIR / "eva_allowed_paths.json"
ALLOWED_PATHS_EXAMPLE_PATH = DATA_DIR / "eva_allowed_paths.example.json"

MAX_LIST_ITEMS = 200
MAX_READ_BYTES = 350_000
MAX_PROMPT_CHARS = 80_000

READABLE_EXTENSIONS = {
    ".bat",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".env.example",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".md",
    ".mdx",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

BLOCKED_NAMES = {
    ".env",
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}

BLOCKED_SUFFIXES = {
    ".sqlite",
    ".db",
    ".key",
    ".pem",
    ".pfx",
    ".p12",
    ".exe",
    ".dll",
    ".zip",
    ".7z",
    ".rar",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
}


def ensure_allowed_paths_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if ALLOWED_PATHS_PATH.exists():
        return

    if ALLOWED_PATHS_EXAMPLE_PATH.exists():
        shutil.copyfile(ALLOWED_PATHS_EXAMPLE_PATH, ALLOWED_PATHS_PATH)
    else:
        ALLOWED_PATHS_PATH.write_text(
            json.dumps(
                {
                    "allowed_roots": [
                        {
                            "name": "Eva project",
                            "path": ".",
                            "description": "Repo Eva local",
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _resolve_config_path(path_value: str) -> Path:
    raw_path = Path(path_value).expanduser()
    if not raw_path.is_absolute():
        raw_path = PROJECT_ROOT / raw_path
    return raw_path.resolve()


def load_allowed_roots() -> list[AllowedRoot]:
    ensure_allowed_paths_file()

    try:
        payload = json.loads(ALLOWED_PATHS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LocalFileError("data/eva_allowed_paths.json contient du JSON invalide.") from exc
    except OSError as exc:
        raise LocalFileError("Impossible de lire data/eva_allowed_paths.json.") from exc

    roots = payload.get("allowed_roots", [])
    if not isinstance(roots, list):
        raise LocalFileError("allowed_roots doit etre une liste.")

    loaded_roots: list[AllowedRoot] = []
    for root in roots:
        if not isinstance(root, dict):
            continue

        name = str(root.get("name", "")).strip()
        path_value = str(root.get("path", "")).strip()
        description = str(root.get("description", "")).strip()

        if not name or not path_value:
            continue

        resolved_path = _resolve_config_path(path_value)
        if resolved_path.exists() and resolved_path.is_dir():
            loaded_roots.append(
                AllowedRoot(name=name, path=resolved_path, description=description)
            )

    if not loaded_roots:
        raise LocalFileError("Aucun dossier autorise valide n'est configure.")

    return loaded_roots


def roots_to_dicts() -> list[dict[str, str]]:
    return [
        {
            "name": root.name,
            "path": str(root.path),
            "description": root.description,
        }
        for root in load_allowed_roots()
    ]


def _get_root(root_name: str) -> AllowedRoot:
    for root in load_allowed_roots():
        if root.name.lower() == root_name.lower():
            return root

    raise LocalFileError(f"Dossier autorise introuvable: {root_name}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_blocked_part(path: Path) -> bool:
    return any(part in BLOCKED_NAMES for part in path.parts)


def resolve_allowed_path(root_name: str, relative_path: str = ".") -> tuple[AllowedRoot, Path]:
    root = _get_root(root_name)
    candidate = (root.path / relative_path).resolve()

    if not _is_relative_to(candidate, root.path):
        raise LocalFileError("Chemin refuse: il sort du dossier autorise.")

    if _has_blocked_part(candidate.relative_to(root.path)):
        raise LocalFileError("Chemin refuse: dossier ou fichier sensible bloque.")

    if not candidate.exists():
        raise LocalFileError("Chemin introuvable dans le dossier autorise.")

    return root, candidate


def _is_readable_file(path: Path) -> bool:
    if not path.is_file():
        return False

    lower_name = path.name.lower()
    if lower_name in BLOCKED_NAMES:
        return False

    suffix = path.suffix.lower()
    if suffix in BLOCKED_SUFFIXES:
        return False

    if lower_name.endswith(".env.example"):
        return True

    return suffix in READABLE_EXTENSIONS


def list_directory(root_name: str, relative_path: str = ".") -> dict[str, Any]:
    root, directory = resolve_allowed_path(root_name, relative_path)
    if not directory.is_dir():
        raise LocalFileError("Le chemin demande n'est pas un dossier.")

    entries = []
    for child in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        if child.name in BLOCKED_NAMES or child.name.startswith("."):
            continue

        relative_child = child.relative_to(root.path).as_posix()
        entries.append(
            {
                "name": child.name,
                "path": relative_child,
                "type": "directory" if child.is_dir() else "file",
                "size": child.stat().st_size if child.is_file() else None,
                "readable": _is_readable_file(child),
            }
        )

        if len(entries) >= MAX_LIST_ITEMS:
            break

    return {
        "root": root.name,
        "path": directory.relative_to(root.path).as_posix(),
        "items": entries,
    }


def read_text_file(root_name: str, relative_path: str) -> dict[str, Any]:
    root, file_path = resolve_allowed_path(root_name, relative_path)

    if not _is_readable_file(file_path):
        raise LocalFileError("Fichier refuse ou type de fichier non lisible en texte.")

    size = file_path.stat().st_size
    if size > MAX_READ_BYTES:
        raise LocalFileError(
            f"Fichier trop volumineux pour cette version. Maximum: {MAX_READ_BYTES} octets."
        )

    raw = file_path.read_bytes()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("utf-8", errors="replace")

    truncated = len(content) > MAX_PROMPT_CHARS
    if truncated:
        content = content[:MAX_PROMPT_CHARS]

    return {
        "root": root.name,
        "path": file_path.relative_to(root.path).as_posix(),
        "size": size,
        "truncated": truncated,
        "content": content,
    }


def search_files(query: str, root_name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    clean_query = query.strip().lower()
    if not clean_query:
        raise LocalFileError("Recherche vide.")

    roots = load_allowed_roots()
    if root_name:
        roots = [_get_root(root_name)]

    safe_limit = min(max(limit, 1), 200)
    results: list[dict[str, Any]] = []

    for root in roots:
        for path in root.path.rglob("*"):
            if len(results) >= safe_limit:
                return results

            try:
                relative_path = path.relative_to(root.path)
            except ValueError:
                continue

            if _has_blocked_part(relative_path) or any(part.startswith(".") for part in relative_path.parts):
                continue

            if clean_query not in path.name.lower() and clean_query not in relative_path.as_posix().lower():
                continue

            results.append(
                {
                    "root": root.name,
                    "path": relative_path.as_posix(),
                    "type": "directory" if path.is_dir() else "file",
                    "readable": _is_readable_file(path),
                }
            )

    return results


def find_unique_readable_file(path_hint: str) -> tuple[str, str] | None:
    clean_hint = path_hint.strip().strip("\"'`")
    if not clean_hint:
        return None

    hinted_path = Path(clean_hint)
    for root in load_allowed_roots():
        candidate = (root.path / hinted_path).resolve()
        if _is_relative_to(candidate, root.path) and candidate.exists() and _is_readable_file(candidate):
            return root.name, candidate.relative_to(root.path).as_posix()

    matches = [
        item
        for item in search_files(Path(clean_hint).name, limit=20)
        if item["type"] == "file" and item["readable"]
    ]

    if len(matches) == 1:
        return str(matches[0]["root"]), str(matches[0]["path"])

    return None
