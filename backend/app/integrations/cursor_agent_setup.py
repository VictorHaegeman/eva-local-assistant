import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.integrations.browser import open_url
from app.integrations.cli_tools import find_cursor_agent


class CursorAgentSetupError(Exception):
    """Raised when Eva cannot inspect or install Cursor Agent."""


CURSOR_AGENT_DOCS_URL = "https://docs.cursor.com/en/cli/overview"
CURSOR_AGENT_INSTALL_COMMAND = "curl https://cursor.com/install -fsS | bash"


def _run(command: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def _wsl_available() -> bool:
    if not shutil.which("wsl.exe"):
        return False
    try:
        completed = _run(["wsl.exe", "bash", "-lc", "printf ok"], timeout=15.0)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and "ok" in completed.stdout


def _cursor_agent_in_wsl() -> str:
    if not shutil.which("wsl.exe"):
        return ""
    try:
        completed = _run(
            [
                "wsl.exe",
                "bash",
                "-lc",
                "command -v cursor-agent || test -x ~/.local/bin/cursor-agent && echo ~/.local/bin/cursor-agent",
            ],
            timeout=20.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""


def cursor_agent_setup_status() -> dict[str, Any]:
    windows_path = find_cursor_agent()
    wsl_available = _wsl_available()
    wsl_path = _cursor_agent_in_wsl() if wsl_available else ""
    installed = bool(windows_path or wsl_path)
    return {
        "installed": installed,
        "windows_path": windows_path,
        "wsl_available": wsl_available,
        "wsl_path": wsl_path,
        "docs_url": CURSOR_AGENT_DOCS_URL,
        "install_command": CURSOR_AGENT_INSTALL_COMMAND,
    }


def _install_in_wsl() -> dict[str, Any]:
    if not _wsl_available():
        return {
            "attempted": False,
            "success": False,
            "message": "WSL indisponible: Cursor Agent officiel s'installe via macOS, Linux ou Windows WSL.",
        }

    command = (
        "set -e; "
        f"{CURSOR_AGENT_INSTALL_COMMAND}; "
        "export PATH=\"$HOME/.local/bin:$PATH\"; "
        "cursor-agent --version || ~/.local/bin/cursor-agent --version"
    )
    try:
        completed = _run(["wsl.exe", "bash", "-lc", command], timeout=240.0)
    except subprocess.TimeoutExpired as exc:
        raise CursorAgentSetupError("Installation cursor-agent trop longue ou bloquee.") from exc
    except OSError as exc:
        raise CursorAgentSetupError("Impossible de lancer WSL pour installer cursor-agent.") from exc

    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    return {
        "attempted": True,
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "output": output[-4000:],
    }


def setup_cursor_agent(auto_install: bool = True, open_docs_on_block: bool = True) -> dict[str, Any]:
    before = cursor_agent_setup_status()
    if before["installed"]:
        return {
            "status": "ready",
            "before": before,
            "after": before,
            "install": {"attempted": False, "success": True, "message": "cursor-agent deja disponible."},
        }

    install_result: dict[str, Any] = {"attempted": False, "success": False}
    if auto_install:
        install_result = _install_in_wsl()

    after = cursor_agent_setup_status()
    if not after["installed"] and open_docs_on_block:
        open_url(CURSOR_AGENT_DOCS_URL)

    return {
        "status": "ready" if after["installed"] else "blocked",
        "before": before,
        "after": after,
        "install": install_result,
    }


def format_cursor_agent_setup_response(result: dict[str, Any]) -> str:
    status = str(result.get("status", "blocked"))
    before = result.get("before", {}) if isinstance(result.get("before"), dict) else {}
    after = result.get("after", {}) if isinstance(result.get("after"), dict) else {}
    install = result.get("install", {}) if isinstance(result.get("install"), dict) else {}

    lines = ["Cursor Agent setup."]
    if status == "ready":
        path = after.get("windows_path") or after.get("wsl_path") or "detecte"
        lines.append(f"Statut: disponible ({path}).")
        if install.get("attempted"):
            lines.append("Installation WSL executee et verifiee.")
        else:
            lines.append("Aucune installation necessaire.")
    else:
        lines.append("Statut: bloque pour l'instant.")
        lines.append(
            "Cursor Agent officiel fonctionne via macOS, Linux ou Windows WSL; "
            "je n'ai pas trouve une installation exploitable."
        )
        if not before.get("wsl_available"):
            lines.append("Cause probable: WSL absent ou non initialise sur ce PC.")
        if install.get("attempted"):
            lines.append(f"Code retour installation: {install.get('returncode')}.")
        if install.get("message"):
            lines.append(str(install["message"]))
        lines.append(f"Docs ouvertes: {CURSOR_AGENT_DOCS_URL}")

    output = str(install.get("output", "")).strip()
    if output:
        lines.append("")
        lines.append("Sortie installation:")
        lines.append(output[-1800:])

    lines.append("")
    lines.append("Commande officielle Cursor CLI:")
    lines.append(CURSOR_AGENT_INSTALL_COMMAND)
    lines.append("")
    lines.append("Verification:")
    lines.append("cursor-agent --version")
    return "\n".join(lines)
