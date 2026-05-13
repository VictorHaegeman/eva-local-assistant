import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class BriefStoreError(Exception):
    """Raised when Eva cannot read or write morning briefs."""


@dataclass(frozen=True)
class Brief:
    id: int
    created_at: str
    title: str
    content: str
    items: list[dict[str, Any]]


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
BRIEFS_DB_PATH = DATA_DIR / "eva_briefs.sqlite"


def init_brief_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(BRIEFS_DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS briefs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    items_json TEXT NOT NULL
                )
                """
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise BriefStoreError("Impossible d'initialiser les briefs locaux.") from exc


def _connect() -> sqlite3.Connection:
    init_brief_store()
    connection = sqlite3.connect(BRIEFS_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def save_brief(title: str, content: str, items: list[dict[str, Any]]) -> Brief:
    created_at = datetime.now(UTC).isoformat()
    items_json = json.dumps(items, ensure_ascii=False)

    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO briefs (created_at, title, content, items_json)
                VALUES (?, ?, ?, ?)
                """,
                (created_at, title, content, items_json),
            )
            connection.commit()
            brief_id = int(cursor.lastrowid)
    except sqlite3.Error as exc:
        raise BriefStoreError("Impossible d'enregistrer le brief local.") from exc

    return Brief(
        id=brief_id,
        created_at=created_at,
        title=title,
        content=content,
        items=items,
    )


def get_latest_brief() -> Brief | None:
    try:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT id, created_at, title, content, items_json
                FROM briefs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error as exc:
        raise BriefStoreError("Impossible de lire le dernier brief local.") from exc

    if not row:
        return None

    return Brief(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        title=str(row["title"]),
        content=str(row["content"]),
        items=json.loads(str(row["items_json"])),
    )


def brief_to_dict(brief: Brief) -> dict[str, Any]:
    return {
        "id": brief.id,
        "created_at": brief.created_at,
        "title": brief.title,
        "content": brief.content,
        "items": brief.items,
    }
