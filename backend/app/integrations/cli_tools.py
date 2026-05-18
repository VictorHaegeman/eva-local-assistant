import os
import shutil
from pathlib import Path


def _existing(paths: list[Path]) -> str:
    for path in paths:
        if path.exists() and path.is_file():
            return str(path)
    return ""


def find_gh() -> str:
    resolved = shutil.which("gh")
    if resolved:
        return resolved

    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    candidates: list[Path] = []
    if program_files:
        candidates.append(Path(program_files) / "GitHub CLI" / "gh.exe")
    if program_files_x86:
        candidates.append(Path(program_files_x86) / "GitHub CLI" / "gh.exe")
    return _existing(candidates)


def find_cursor_agent() -> str:
    resolved = shutil.which("cursor-agent")
    if resolved:
        return resolved

    home = Path.home()
    local_app_data = os.environ.get("LOCALAPPDATA")
    candidates = [
        home / ".local" / "bin" / "cursor-agent",
        home / ".local" / "bin" / "cursor-agent.exe",
    ]
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "cursor-agent" / "cursor-agent.exe")
    return _existing(candidates)
