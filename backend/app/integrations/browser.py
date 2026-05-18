import os
import shutil
import subprocess
from pathlib import Path

from app.config import settings


def _browser_candidates() -> list[str]:
    candidates: list[str] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")

    brave_paths = []
    if local_app_data:
        brave_paths.append(
            Path(local_app_data) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
        )
    if program_files:
        brave_paths.append(
            Path(program_files) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
        )
    if program_files_x86:
        brave_paths.append(
            Path(program_files_x86) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
        )

    chrome_paths = []
    edge_paths = []
    if program_files:
        chrome_paths.append(Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe")
        edge_paths.append(Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    if program_files_x86:
        chrome_paths.append(Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe")
        edge_paths.append(Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe")

    preference = settings.eva_browser_preference.strip().lower()
    groups = {
        "brave": brave_paths,
        "chrome": chrome_paths,
        "edge": edge_paths,
    }

    preferred = groups.get(preference, brave_paths)
    for group in (preferred, brave_paths, chrome_paths, edge_paths):
        candidates.extend(str(path) for path in group)

    return candidates


def find_browser() -> str:
    for candidate in _browser_candidates():
        if Path(candidate).exists():
            return candidate

    preference = settings.eva_browser_preference.strip().lower()
    command_order = {
        "brave": ("brave.exe", "brave", "chrome.exe", "msedge.exe"),
        "chrome": ("chrome.exe", "brave.exe", "msedge.exe"),
        "edge": ("msedge.exe", "brave.exe", "chrome.exe"),
    }.get(preference, ("brave.exe", "brave", "chrome.exe", "msedge.exe"))

    for command in command_order:
        resolved = shutil.which(command)
        if resolved:
            return resolved

    return ""


def open_url(url: str, app_mode: bool = False) -> None:
    browser = find_browser()
    if browser:
        args = [browser, url]
        if app_mode:
            args = [browser, f"--app={url}", "--new-window"]
        subprocess.Popen(args, shell=False)
        return

    subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
