import json
import shutil
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.integrations.cli_tools import find_cursor_agent


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
CURSOR_AGENT_LOG_DIR = DATA_DIR / "cursor_agent_logs"
RUN_EVENTS_PATH = CURSOR_AGENT_LOG_DIR / "project_factory_runs.jsonl"


class ProjectFactoryAgentError(Exception):
    """Raised when Eva cannot launch or supervise cursor-agent for Project Factory."""


IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".next",
    ".turbo",
}

IMPLEMENTATION_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".scss",
    ".json",
}


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _notify_telegram(message: str) -> None:
    token = settings.eva_telegram_bot_token.strip()
    chat_id = settings.eva_telegram_allowed_chat_id.strip()
    if not settings.eva_telegram_enabled or not token or not chat_id:
        return

    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message[:3500]},
            timeout=15.0,
        )
    except Exception:
        pass


def _append_run_event(event: dict[str, object]) -> None:
    CURSOR_AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        **event,
    }
    with RUN_EVENTS_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _resolve_workspace(path_value: str) -> Path:
    workspace = Path(path_value).expanduser().resolve()
    if not workspace.name:
        raise ProjectFactoryAgentError("Chemin projet invalide.")
    if not workspace.exists():
        raise ProjectFactoryAgentError("Workspace introuvable. Cree-le d'abord.")
    return workspace


def _iter_project_files(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for path in workspace.rglob("*"):
        if path.is_dir():
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(workspace).parts):
            continue
        files.append(path)
    return files


def audit_project_workspace(workspace: Path) -> dict[str, object]:
    files = _iter_project_files(workspace)
    relative_files = [path.relative_to(workspace).as_posix() for path in files]
    implementation_files = [
        path
        for path in files
        if path.suffix.lower() in IMPLEMENTATION_SUFFIXES
        and path.name not in {"package-lock.json"}
        and not path.name.endswith("_PROMPT.md")
    ]

    readme_path = workspace / "README.md"
    readme = readme_path.read_text(encoding="utf-8", errors="replace") if readme_path.exists() else ""
    package_exists = (workspace / "package.json").exists()
    python_entry_exists = any(
        (workspace / candidate).exists()
        for candidate in ("main.py", "app.py", "requirements.txt", "pyproject.toml")
    )

    failures: list[str] = []
    warnings: list[str] = []
    if not readme_path.exists():
        failures.append("README.md absent.")
    elif "A completer apres generation du projet" in readme:
        failures.append("README.md encore au stade scaffold.")

    if len(implementation_files) < 3:
        failures.append("Trop peu de fichiers d'implementation detectes.")

    if not package_exists and not python_entry_exists:
        warnings.append("Aucun package.json ou entree Python claire detectee.")

    if not (workspace / ".git").exists():
        warnings.append("Git n'est pas initialise dans le workspace.")

    score = 100 - (len(failures) * 35) - (len(warnings) * 10)
    score = max(0, min(100, score))
    status = "pass" if not failures else "fail"
    if status == "pass" and warnings:
        status = "warning"

    return {
        "status": status,
        "score": score,
        "failures": failures,
        "warnings": warnings,
        "file_count": len(files),
        "implementation_file_count": len(implementation_files),
        "files": relative_files[:120],
    }


def _log_tail(path: Path, max_chars: int = 6000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-max_chars:]


def _repair_prompt(
    project_name: str,
    original_prompt: str,
    audit: dict[str, object],
    log_path: Path,
) -> str:
    return f"""
Tu es cursor-agent dans le projet {project_name}.

Eva a lance une premiere generation mais l'audit local n'est pas satisfaisant.

Prompt initial:
{original_prompt}

Audit local:
{json.dumps(audit, indent=2, ensure_ascii=False)}

Extrait du log precedent:
{_log_tail(log_path)}

Objectif:
1. Corrige les points d'audit en priorite.
2. Ajoute une vraie V1 executable, pas seulement des fichiers de cadrage.
3. Complete README.md avec les commandes de lancement.
4. Garde les changements simples, maintenables et gratuits/local-first.
5. N'ajoute aucun secret, aucune API payante obligatoire, aucun appel OpenAI dans le projet.
""".strip()


def _run_cursor_agent(
    workspace: Path,
    prompt: str,
    project_name: str,
    suffix: str,
) -> tuple[int, Path]:
    cursor_agent = find_cursor_agent()
    if not cursor_agent:
        raise ProjectFactoryAgentError("cursor-agent introuvable dans le PATH.")

    CURSOR_AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = CURSOR_AGENT_LOG_DIR / f"{workspace.name}-{_utc_stamp()}-{suffix}.log"
    command = [
        cursor_agent,
        "-p",
        prompt,
        "--output-format",
        "text",
    ]
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"Project: {project_name}\nWorkspace: {workspace}\n\n")
        process = subprocess.run(
            command,
            cwd=str(workspace),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=settings.eva_project_factory_agent_timeout_seconds,
        )
    return process.returncode, log_path


def _run_git_commit(workspace: Path, message: str) -> str:
    if not shutil.which("git"):
        return "Git introuvable, commit ignore."

    outputs: list[str] = []
    if not (workspace / ".git").exists():
        subprocess.run(["git", "init"], cwd=str(workspace), capture_output=True, text=True, timeout=30)

    subprocess.run(["git", "add", "."], cwd=str(workspace), capture_output=True, text=True, timeout=60)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if not status.stdout.strip():
        return "Aucun changement a commit apres cursor-agent."

    completed = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=120,
    )
    outputs.append(f"git commit exit_code={completed.returncode}")
    if completed.stdout:
        outputs.append(completed.stdout[-4000:])
    if completed.stderr:
        outputs.append(completed.stderr[-4000:])
    return "\n".join(outputs)


def _run_git_push(workspace: Path) -> str:
    if not settings.eva_project_factory_auto_push:
        return "Push automatique desactive."
    if not shutil.which("git"):
        return "Git introuvable, push ignore."

    branch = "main"
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if current_branch.stdout.strip():
        branch = current_branch.stdout.strip()

    completed = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = [f"git push exit_code={completed.returncode}"]
    if completed.stdout:
        output.append(completed.stdout[-4000:])
    if completed.stderr:
        output.append(completed.stderr[-4000:])
    return "\n".join(output)


def _write_audit(workspace: Path, audit: dict[str, object], suffix: str) -> Path:
    CURSOR_AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = CURSOR_AGENT_LOG_DIR / f"{workspace.name}-{_utc_stamp()}-{suffix}-audit.json"
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    return audit_path


def _supervise_project_run(payload: dict[str, object]) -> None:
    workspace = _resolve_workspace(str(payload.get("workspace_path", "")))
    project_name = str(payload.get("project_name", workspace.name))
    prompt = str(payload.get("cursor_prompt", "") or payload.get("prompt", "")).strip()
    if not prompt:
        prompt = (workspace / "CURSOR_PROMPT.md").read_text(encoding="utf-8", errors="replace")

    event_base = {
        "project_name": project_name,
        "workspace_path": str(workspace),
    }
    _append_run_event({**event_base, "event": "started"})
    _notify_telegram(f"Eva lance cursor-agent pour {project_name}.\nWorkspace: {workspace}")

    try:
        first_code, first_log = _run_cursor_agent(workspace, prompt, project_name, "initial")
        first_audit = audit_project_workspace(workspace)
        first_audit_path = _write_audit(workspace, first_audit, "initial")
        _append_run_event(
            {
                **event_base,
                "event": "initial_finished",
                "return_code": first_code,
                "log_path": str(first_log),
                "audit_path": str(first_audit_path),
                "audit": first_audit,
            }
        )

        final_audit = first_audit
        final_log = first_log
        repaired = False
        if first_audit["status"] == "fail" and settings.eva_project_factory_agent_repair_once:
            repaired = True
            repair_prompt = _repair_prompt(project_name, prompt, first_audit, first_log)
            repair_code, repair_log = _run_cursor_agent(workspace, repair_prompt, project_name, "repair")
            final_audit = audit_project_workspace(workspace)
            repair_audit_path = _write_audit(workspace, final_audit, "repair")
            final_log = repair_log
            _append_run_event(
                {
                    **event_base,
                    "event": "repair_finished",
                    "return_code": repair_code,
                    "log_path": str(repair_log),
                    "audit_path": str(repair_audit_path),
                    "audit": final_audit,
                }
            )

        commit_result = ""
        push_result = ""
        if settings.eva_project_factory_agent_auto_commit:
            commit_result = _run_git_commit(workspace, "Implement V1 with Cursor Agent")
            push_result = _run_git_push(workspace)

        _append_run_event(
            {
                **event_base,
                "event": "completed",
                "repaired": repaired,
                "final_log_path": str(final_log),
                "final_audit": final_audit,
                "commit_result": commit_result[-4000:],
                "push_result": push_result[-4000:],
            }
        )
        _notify_telegram(
            f"Project Factory termine pour {project_name}.\n"
            f"Audit: {final_audit['status']} ({final_audit['score']}/100)\n"
            f"Fichiers: {final_audit['file_count']}, implementation: {final_audit['implementation_file_count']}\n"
            f"Repair lance: {repaired}\n"
            f"Log: {final_log}"
        )
    except Exception as exc:
        _append_run_event({**event_base, "event": "failed", "error": str(exc)})
        _notify_telegram(f"Project Factory a echoue pour {project_name}: {exc}")


def start_project_factory_agent(payload: dict[str, object]) -> dict[str, object]:
    if not settings.eva_project_factory_auto_cursor_agent:
        return {
            "started": False,
            "available": bool(find_cursor_agent()),
            "message": "Auto cursor-agent desactive.",
        }

    cursor_agent = find_cursor_agent()
    if not cursor_agent:
        return {
            "started": False,
            "available": False,
            "message": "cursor-agent introuvable: Eva a cree le projet et le prompt, mais ne peut pas coder la V1 seule.",
        }

    workspace = _resolve_workspace(str(payload.get("workspace_path", "")))
    thread = threading.Thread(
        target=_supervise_project_run,
        args=(payload,),
        daemon=True,
        name=f"eva-project-factory-{workspace.name}",
    )
    thread.start()
    return {
        "started": True,
        "available": True,
        "workspace_path": str(workspace),
        "runs_log": str(RUN_EVENTS_PATH),
        "message": "cursor-agent lance en arriere-plan avec audit et relance automatique si besoin.",
    }


def list_project_factory_agent_events(limit: int = 30) -> list[dict[str, object]]:
    if not RUN_EVENTS_PATH.exists():
        return []

    events: list[dict[str, object]] = []
    with RUN_EVENTS_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
    safe_limit = min(max(limit, 1), 200)
    return events[-safe_limit:][::-1]
