import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TaskStoreError(Exception):
    """Raised when Eva cannot read or write local project tasks."""


@dataclass(frozen=True)
class ProjectTask:
    id: int
    project: str
    title: str
    description: str
    priority: str
    status: str
    created_at: str


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
TASKS_DB_PATH = DATA_DIR / "eva_tasks.sqlite"


def init_task_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(TASKS_DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS project_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal',
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise TaskStoreError("Impossible d'initialiser les taches locales.") from exc


def _connect() -> sqlite3.Connection:
    init_task_store()
    connection = sqlite3.connect(TASKS_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_task(
    project: str,
    title: str,
    description: str = "",
    priority: str = "normal",
) -> ProjectTask:
    clean_project = project.strip()
    clean_title = " ".join(title.strip().split())
    clean_description = " ".join(description.strip().split())
    clean_priority = priority.strip().lower() or "normal"

    if not clean_project or not clean_title:
        raise TaskStoreError("Projet et titre de tache obligatoires.")

    if clean_priority not in {"low", "normal", "high"}:
        clean_priority = "normal"

    created_at = datetime.now(UTC).isoformat()

    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO project_tasks (project, title, description, priority, status, created_at)
                VALUES (?, ?, ?, ?, 'open', ?)
                """,
                (clean_project, clean_title, clean_description, clean_priority, created_at),
            )
            connection.commit()
            task_id = int(cursor.lastrowid)
    except sqlite3.Error as exc:
        raise TaskStoreError("Impossible de creer la tache locale.") from exc

    return ProjectTask(
        id=task_id,
        project=clean_project,
        title=clean_title,
        description=clean_description,
        priority=clean_priority,
        status="open",
        created_at=created_at,
    )


def list_tasks(project: str | None = None, limit: int = 100) -> list[ProjectTask]:
    safe_limit = min(max(limit, 1), 300)

    try:
        with _connect() as connection:
            if project:
                rows = connection.execute(
                    """
                    SELECT id, project, title, description, priority, status, created_at
                    FROM project_tasks
                    WHERE lower(project) = lower(?)
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (project, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, project, title, description, priority, status, created_at
                    FROM project_tasks
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
    except sqlite3.Error as exc:
        raise TaskStoreError("Impossible de lire les taches locales.") from exc

    return [
        ProjectTask(
            id=int(row["id"]),
            project=str(row["project"]),
            title=str(row["title"]),
            description=str(row["description"]),
            priority=str(row["priority"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
        )
        for row in rows
    ]


def delete_task(task_id: int, project: str | None = None) -> bool:
    try:
        with _connect() as connection:
            if project:
                cursor = connection.execute(
                    "DELETE FROM project_tasks WHERE id = ? AND lower(project) = lower(?)",
                    (task_id, project),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM project_tasks WHERE id = ?",
                    (task_id,),
                )
            connection.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        raise TaskStoreError("Impossible de supprimer cette tache locale.") from exc


def task_to_dict(task: ProjectTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "project": task.project,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": task.status,
        "created_at": task.created_at,
    }
