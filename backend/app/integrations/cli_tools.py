import os
import shutil
import subprocess
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
    command = find_cursor_agent_command()
    if command:
        return " ".join(command)
    return ""


def _cursor_agent_binary_candidates() -> list[Path]:
    home = Path.home()
    local_app_data = os.environ.get("LOCALAPPDATA")
    candidates = [
        home / ".local" / "bin" / "cursor-agent",
        home / ".local" / "bin" / "cursor-agent.exe",
    ]
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "cursor-agent" / "cursor-agent.exe")
    return candidates


def _cursor_subcommand_available(cursor_path: str) -> bool:
    try:
        completed = subprocess.run(
            [cursor_path, "agent", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def find_cursor_agent_command() -> list[str]:
    resolved = shutil.which("cursor-agent")
    if resolved:
        return [resolved]

    existing_binary = _existing(_cursor_agent_binary_candidates())
    if existing_binary:
        return [existing_binary]

    cursor = shutil.which("cursor")
    if cursor and _cursor_subcommand_available(cursor):
        return [cursor, "agent"]

    return []


def is_gh_authenticated() -> bool:
    gh = find_gh()
    if not gh:
        return False

    try:
        completed = subprocess.run(
            [gh, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return completed.returncode == 0
