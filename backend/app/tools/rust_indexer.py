import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.files.local_files import _has_blocked_part, _is_readable_file


class RustIndexerError(Exception):
    """Raised when Eva cannot run the optional Rust indexer."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SIDECAR_DIR = PROJECT_ROOT / "sidecars" / "eva-rust-indexer"
BINARY_NAME = "eva-rust-indexer.exe" if os.name == "nt" else "eva-rust-indexer"
RELEASE_BINARY = SIDECAR_DIR / "target" / "release" / BINARY_NAME
DEBUG_BINARY = SIDECAR_DIR / "target" / "debug" / BINARY_NAME


def _binary_path() -> Path | None:
    for candidate in (RELEASE_BINARY, DEBUG_BINARY):
        if candidate.exists():
            return candidate
    return None


def rust_indexer_status() -> dict[str, object]:
    binary = _binary_path()
    return {
        "source_exists": SIDECAR_DIR.exists(),
        "cargo_available": shutil.which("cargo") is not None,
        "binary_exists": binary is not None,
        "binary_path": str(binary) if binary else "",
        "sidecar_dir": str(SIDECAR_DIR),
        "engine": "rust" if binary else "python_fallback",
        "build_command": "cd sidecars/eva-rust-indexer && cargo build --release",
    }


def _python_scan(root: Path, max_items: int) -> dict[str, object]:
    items: list[dict[str, object]] = []
    extensions: dict[str, int] = {}
    files = 0
    directories = 0
    skipped = 0

    for path in root.rglob("*"):
        if len(items) >= max_items:
            break

        try:
            relative = path.relative_to(root)
        except ValueError:
            continue

        if _has_blocked_part(relative) or any(part.startswith(".") for part in relative.parts):
            skipped += 1
            if path.is_dir():
                continue
            continue

        if path.is_dir():
            directories += 1
            items.append(
                {
                    "path": relative.as_posix(),
                    "type": "directory",
                    "extension": "",
                    "size": 0,
                    "readable": False,
                }
            )
            continue

        if not path.is_file():
            skipped += 1
            continue

        suffix = path.suffix.lower().lstrip(".")
        files += 1
        if suffix:
            extensions[suffix] = extensions.get(suffix, 0) + 1
        items.append(
            {
                "path": relative.as_posix(),
                "type": "file",
                "extension": suffix,
                "size": path.stat().st_size,
                "readable": _is_readable_file(path),
            }
        )

    return {
        "engine": "python_fallback",
        "root": str(root),
        "max_items": max_items,
        "files": files,
        "directories": directories,
        "skipped": skipped,
        "extensions": extensions,
        "items": items,
    }


def scan_path(path: str | Path, max_items: int = 500) -> dict[str, Any]:
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise RustIndexerError("Dossier introuvable pour l'indexation.")

    safe_limit = min(max(max_items, 1), 5000)
    binary = _binary_path()
    if not binary:
        return _python_scan(root, safe_limit)

    try:
        completed = subprocess.run(
            [str(binary), str(root), str(safe_limit)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except subprocess.SubprocessError as exc:
        raise RustIndexerError("Le sidecar Rust n'a pas pu scanner ce dossier.") from exc

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RustIndexerError("Le sidecar Rust a renvoye un JSON invalide.") from exc

    if not isinstance(payload, dict):
        raise RustIndexerError("Le sidecar Rust a renvoye un format inattendu.")

    return payload
