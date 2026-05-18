import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class ChatHistoryError(Exception):
    """Raised when Eva cannot persist or load chat history."""


@dataclass(frozen=True)
class ChatSession:
    id: str
    channel: str
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChatHistoryMessage:
    id: int
    session_id: str
    role: str
    content: str
    created_at: str


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
CHAT_HISTORY_DB_PATH = DATA_DIR / "eva_chat_history.sqlite"


def init_chat_history_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(CHAT_HISTORY_DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
                )
                """
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ChatHistoryError("Impossible d'initialiser l'historique de chat.") from exc


def _connect() -> sqlite3.Connection:
    init_chat_history_store()
    connection = sqlite3.connect(CHAT_HISTORY_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _title_from_text(text: str) -> str:
    clean = " ".join(text.strip().split())
    return clean[:80] or "Nouvelle conversation"


def ensure_chat_session(
    session_id: str | None = None,
    channel: str = "web",
    title: str = "Nouvelle conversation",
) -> ChatSession:
    clean_session_id = (session_id or "").strip() or f"{channel}-{uuid4().hex[:16]}"
    clean_channel = channel.strip()[:40] or "web"
    clean_title = _title_from_text(title)
    now = _now()

    try:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT id, channel, title, created_at, updated_at
                FROM chat_sessions
                WHERE id = ?
                """,
                (clean_session_id,),
            ).fetchone()
            if row:
                return _session_from_row(row)

            connection.execute(
                """
                INSERT INTO chat_sessions (id, channel, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (clean_session_id, clean_channel, clean_title, now, now),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ChatHistoryError("Impossible de creer la session de chat.") from exc

    return ChatSession(
        id=clean_session_id,
        channel=clean_channel,
        title=clean_title,
        created_at=now,
        updated_at=now,
    )


def append_chat_exchange(
    session_id: str | None,
    user_text: str,
    assistant_text: str,
    channel: str = "web",
) -> ChatSession:
    session = ensure_chat_session(session_id, channel=channel, title=user_text)
    now = _now()

    try:
        with _connect() as connection:
            connection.executemany(
                """
                INSERT INTO chat_messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (session.id, "user", user_text[:20_000], now),
                    (session.id, "assistant", assistant_text[:20_000], now),
                ],
            )
            connection.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, session.id),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ChatHistoryError("Impossible d'enregistrer la conversation.") from exc

    return ensure_chat_session(session.id, channel=channel, title=user_text)


def list_chat_sessions(limit: int = 50) -> list[ChatSession]:
    safe_limit = min(max(limit, 1), 200)
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, channel, title, created_at, updated_at
                FROM chat_sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise ChatHistoryError("Impossible de lire les conversations.") from exc

    return [_session_from_row(row) for row in rows]


def get_chat_messages(session_id: str, limit: int = 100) -> list[ChatHistoryMessage]:
    safe_limit = min(max(limit, 1), 300)
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, safe_limit),
            ).fetchall()
    except sqlite3.Error as exc:
        raise ChatHistoryError("Impossible de lire les messages de conversation.") from exc

    return [_message_from_row(row) for row in rows]


def get_recent_chat_messages(session_id: str, limit: int = 40) -> list[ChatHistoryMessage]:
    safe_limit = min(max(limit, 1), 120)
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, safe_limit),
            ).fetchall()
    except sqlite3.Error as exc:
        raise ChatHistoryError("Impossible de lire les messages recents.") from exc

    return [_message_from_row(row) for row in reversed(rows)]


def _session_from_row(row: sqlite3.Row) -> ChatSession:
    return ChatSession(
        id=str(row["id"]),
        channel=str(row["channel"]),
        title=str(row["title"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _message_from_row(row: sqlite3.Row) -> ChatHistoryMessage:
    return ChatHistoryMessage(
        id=int(row["id"]),
        session_id=str(row["session_id"]),
        role=str(row["role"]),
        content=str(row["content"]),
        created_at=str(row["created_at"]),
    )


def chat_session_to_dict(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "channel": session.channel,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def chat_message_to_dict(message: ChatHistoryMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
    }
