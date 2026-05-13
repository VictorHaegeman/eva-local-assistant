import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


ActionStatus = Literal["pending", "approved", "rejected", "executed", "failed"]


class ActionStoreError(Exception):
    """Raised when Eva cannot read or write local actions."""


@dataclass(frozen=True)
class EvaAction:
    id: int
    action_type: str
    title: str
    description: str
    payload: dict[str, Any]
    status: ActionStatus
    created_at: str
    updated_at: str
    result: str


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
ACTIONS_DB_PATH = DATA_DIR / "eva_actions.sqlite"

VALID_STATUSES: set[str] = {"pending", "approved", "rejected", "executed", "failed"}


def init_action_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(ACTIONS_DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ActionStoreError("Impossible d'initialiser les actions locales.") from exc


def _connect() -> sqlite3.Connection:
    init_action_store()
    connection = sqlite3.connect(ACTIONS_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _row_to_action(row: sqlite3.Row) -> EvaAction:
    status = str(row["status"])
    if status not in VALID_STATUSES:
        status = "pending"

    return EvaAction(
        id=int(row["id"]),
        action_type=str(row["action_type"]),
        title=str(row["title"]),
        description=str(row["description"]),
        payload=json.loads(str(row["payload_json"])),
        status=status,  # type: ignore[arg-type]
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        result=str(row["result"]),
    )


def create_action(
    action_type: str,
    title: str,
    description: str,
    payload: dict[str, Any],
) -> EvaAction:
    clean_type = action_type.strip()
    clean_title = " ".join(title.strip().split())
    clean_description = description.strip()

    if not clean_type or not clean_title:
        raise ActionStoreError("Type et titre d'action obligatoires.")

    created_at = datetime.now(UTC).isoformat()
    payload_json = json.dumps(payload, ensure_ascii=False)

    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO actions (
                    action_type, title, description, payload_json,
                    status, created_at, updated_at, result
                )
                VALUES (?, ?, ?, ?, 'pending', ?, ?, '')
                """,
                (
                    clean_type,
                    clean_title,
                    clean_description,
                    payload_json,
                    created_at,
                    created_at,
                ),
            )
            connection.commit()
            action_id = int(cursor.lastrowid)
    except sqlite3.Error as exc:
        raise ActionStoreError("Impossible de creer l'action locale.") from exc

    return get_action(action_id)


def get_action(action_id: int) -> EvaAction:
    try:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT id, action_type, title, description, payload_json,
                       status, created_at, updated_at, result
                FROM actions
                WHERE id = ?
                """,
                (action_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise ActionStoreError("Impossible de lire cette action locale.") from exc

    if not row:
        raise ActionStoreError("Action introuvable.")

    return _row_to_action(row)


def list_actions(status: str | None = None, limit: int = 100) -> list[EvaAction]:
    safe_limit = min(max(limit, 1), 300)

    try:
        with _connect() as connection:
            if status:
                rows = connection.execute(
                    """
                    SELECT id, action_type, title, description, payload_json,
                           status, created_at, updated_at, result
                    FROM actions
                    WHERE status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (status, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, action_type, title, description, payload_json,
                           status, created_at, updated_at, result
                    FROM actions
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
    except sqlite3.Error as exc:
        raise ActionStoreError("Impossible de lire les actions locales.") from exc

    return [_row_to_action(row) for row in rows]


def update_action_status(
    action_id: int,
    status: ActionStatus,
    result: str | None = None,
) -> EvaAction:
    updated_at = datetime.now(UTC).isoformat()

    try:
        with _connect() as connection:
            if result is None:
                cursor = connection.execute(
                    "UPDATE actions SET status = ?, updated_at = ? WHERE id = ?",
                    (status, updated_at, action_id),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE actions
                    SET status = ?, updated_at = ?, result = ?
                    WHERE id = ?
                    """,
                    (status, updated_at, result[:40_000], action_id),
                )
            connection.commit()
    except sqlite3.Error as exc:
        raise ActionStoreError("Impossible de mettre a jour cette action locale.") from exc

    if cursor.rowcount == 0:
        raise ActionStoreError("Action introuvable.")

    return get_action(action_id)


def delete_action(action_id: int) -> bool:
    try:
        with _connect() as connection:
            cursor = connection.execute("DELETE FROM actions WHERE id = ?", (action_id,))
            connection.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        raise ActionStoreError("Impossible de supprimer cette action locale.") from exc


def action_to_dict(action: EvaAction) -> dict[str, Any]:
    return {
        "id": action.id,
        "action_type": action.action_type,
        "title": action.title,
        "description": action.description,
        "payload": action.payload,
        "status": action.status,
        "created_at": action.created_at,
        "updated_at": action.updated_at,
        "result": action.result,
    }
