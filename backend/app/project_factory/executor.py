import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.actions.action_store import EvaAction
from app.projects.project_store import PROJECTS_PATH, ensure_projects_file


class ProjectFactoryExecutionError(Exception):
    """Raised when Eva cannot execute a Project Factory action."""


def _resolve_workspace(path_value: str) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.name:
        raise ProjectFactoryExecutionError("Chemin projet invalide.")
    return path


def _write_project_files(workspace: Path, files: dict[str, str]) -> list[str]:
    written: list[str] = []
    for relative_path, content in files.items():
        clean_relative = Path(relative_path)
        if clean_relative.is_absolute() or ".." in clean_relative.parts:
            raise ProjectFactoryExecutionError(f"Chemin fichier refuse: {relative_path}")
        target = (workspace / clean_relative).resolve()
        try:
            target.relative_to(workspace)
        except ValueError as exc:
            raise ProjectFactoryExecutionError(f"Chemin fichier refuse: {relative_path}") from exc

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
    return written


def _register_project(project_name: str, workspace: Path, description: str) -> None:
    ensure_projects_file()
    try:
        payload = json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {"projects": []}

    projects = payload.setdefault("projects", [])
    if not isinstance(projects, list):
        projects = []
        payload["projects"] = projects

    normalized_path = str(workspace)
    for project in projects:
        if not isinstance(project, dict):
            continue
        if str(project.get("path", "")).lower() == normalized_path.lower():
            return

    projects.append(
        {
            "name": project_name,
            "path": normalized_path,
            "description": description,
            "type": "code",
        }
    )
    PROJECTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _run_quiet(command: str, cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        text=True,
        capture_output=True,
        timeout=60,
    )
    output = [f"{command}", f"exit_code={completed.returncode}"]
    if completed.stdout:
        output.append(completed.stdout[-4000:])
    if completed.stderr:
        output.append(completed.stderr[-4000:])
    return "\n".join(output)


def execute_project_workspace_create(action: EvaAction) -> str:
    payload = action.payload
    workspace = _resolve_workspace(str(payload.get("workspace_path", "")))
    files_payload = payload.get("files", {})
    if not isinstance(files_payload, dict):
        raise ProjectFactoryExecutionError("Payload fichiers invalide.")

    files = {str(key): str(value) for key, value in files_payload.items()}
    workspace.mkdir(parents=True, exist_ok=True)
    written = _write_project_files(workspace, files)
    project_name = str(payload.get("project_name", workspace.name))
    idea = str(payload.get("idea", "Projet prepare par Eva."))
    _register_project(project_name, workspace, idea[:400])

    git_result = ""
    if shutil.which("git"):
        git_dir = workspace / ".git"
        if not git_dir.exists():
            git_result = _run_quiet("git init", workspace)

    return "\n".join(
        [
            f"Workspace cree: {workspace}",
            f"Fichiers ecrits: {len(written)}",
            *[f"- {path}" for path in written],
            "Projet ajoute a data/eva_projects.json.",
            git_result,
        ]
    ).strip()


def execute_clipboard_set_prompt(action: EvaAction) -> str:
    prompt = str(action.payload.get("prompt", "")).strip()
    if not prompt:
        raise ProjectFactoryExecutionError("Prompt vide.")

    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Set-Clipboard"],
        input=prompt,
        text=True,
        capture_output=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise ProjectFactoryExecutionError(completed.stderr or "Impossible de copier le prompt.")
    return "Prompt copie dans le presse-papiers Windows."


def execute_cursor_open_project(action: EvaAction) -> str:
    workspace = _resolve_workspace(str(action.payload.get("workspace_path", "")))
    if not workspace.exists():
        raise ProjectFactoryExecutionError("Workspace introuvable. Cree-le d'abord.")

    cursor = shutil.which("cursor")
    if not cursor:
        raise ProjectFactoryExecutionError("Cursor CLI introuvable dans le PATH.")

    subprocess.Popen([cursor, str(workspace)], shell=False)
    return f"Cursor ouvert sur: {workspace}"


def execute_github_repo_create(action: EvaAction) -> str:
    workspace = _resolve_workspace(str(action.payload.get("workspace_path", "")))
    repo_name = str(action.payload.get("repo_name", workspace.name)).strip()
    visibility = str(action.payload.get("visibility", "private")).strip().lower()
    if visibility not in {"private", "public"}:
        visibility = "private"

    if not workspace.exists():
        raise ProjectFactoryExecutionError("Workspace introuvable. Cree-le d'abord.")
    gh = shutil.which("gh")
    if not gh:
        raise ProjectFactoryExecutionError("GitHub CLI gh introuvable.")

    auth = subprocess.run([gh, "auth", "status"], text=True, capture_output=True, timeout=20)
    if auth.returncode != 0:
        raise ProjectFactoryExecutionError("GitHub CLI n'est pas connecte. Lance: gh auth login")

    command = [
        gh,
        "repo",
        "create",
        repo_name,
        f"--{visibility}",
        "--source",
        str(workspace),
        "--remote",
        "origin",
    ]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=60)
    output = [f"exit_code={completed.returncode}"]
    if completed.stdout:
        output.append(completed.stdout[-8000:])
    if completed.stderr:
        output.append(completed.stderr[-8000:])
    if completed.returncode != 0:
        raise ProjectFactoryExecutionError("\n".join(output))
    return "\n".join(["Repo GitHub cree via gh CLI.", *output])
