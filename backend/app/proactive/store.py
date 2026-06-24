import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "eva_proactive.sqlite"


class ProactiveStoreError(Exception):
    pass


def _conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_proactive_store() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proactive_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'info',
                created_at TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()


def push_proactive(source: str, content: str, kind: str = "info") -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        cursor = conn.execute(
            "INSERT INTO proactive_messages (source, content, kind, created_at) VALUES (?, ?, ?, ?)",
            (source, content, kind, now),
        )
        conn.commit()
        row_id = cursor.lastrowid
    return {"id": row_id, "source": source, "content": content, "kind": kind, "created_at": now}


def get_pending_proactive(limit: int = 10) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, source, content, kind, created_at FROM proactive_messages "
            "WHERE read = 0 ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_proactive_read(ids: list[int]) -> int:
    if not ids:
        return 0
    with _conn() as conn:
        placeholders = ",".join("?" for _ in ids)
        cursor = conn.execute(
            f"UPDATE proactive_messages SET read = 1 WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()
    return cursor.rowcount


def proactive_store_status() -> dict[str, Any]:
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM proactive_messages").fetchone()[0]
        unread = conn.execute(
            "SELECT COUNT(*) FROM proactive_messages WHERE read = 0"
        ).fetchone()[0]
    return {"total": total, "unread": unread}
