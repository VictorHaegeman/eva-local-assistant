import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ProblemStoreError(Exception):
    """Raised when Eva cannot store or read resolver events."""


@dataclass(frozen=True)
class ProblemEvent:
    id: int
    created_at: str
    message: str
    domain: str
    expected_outcome: str
    problem_type: str
    summary: str
    tool: str
    status: str
    error: str
    alternate_routes: tuple[str, ...]
    safe_actions: tuple[str, ...]
    trusted_actions: bool


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
PROBLEM_DB_PATH = DATA_DIR / "eva_problem_resolver.sqlite"


def init_problem_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(PROBLEM_DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS problem_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    message TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    expected_outcome TEXT NOT NULL,
                    problem_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL,
                    alternate_routes TEXT NOT NULL,
                    safe_actions TEXT NOT NULL,
                    trusted_actions INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ProblemStoreError("Impossible d'initialiser le resolver Eva.") from exc


def _connect() -> sqlite3.Connection:
    init_problem_store()
    connection = sqlite3.connect(PROBLEM_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _compact(value: str, limit: int) -> str:
    cleaned = " ".join(str(value or "").split())
    return cleaned[:limit]


def record_problem_event(
    *,
    message: str,
    domain: str,
    expected_outcome: str,
    problem_type: str,
    summary: str,
    tool: str,
    status: str,
    error: str = "",
    alternate_routes: tuple[str, ...] = (),
    safe_actions: tuple[str, ...] = (),
    trusted_actions: bool = False,
) -> ProblemEvent | None:
    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO problem_events (
                    created_at,
                    message,
                    domain,
                    expected_outcome,
                    problem_type,
                    summary,
                    tool,
                    status,
                    error,
                    alternate_routes,
                    safe_actions,
                    trusted_actions
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    _compact(message, 1500),
                    _compact(domain, 80),
                    _compact(expected_outcome, 80),
                    _compact(problem_type, 80),
                    _compact(summary, 1200),
                    _compact(tool, 120),
                    _compact(status, 40),
                    _compact(error, 1200),
                    json.dumps(list(alternate_routes), ensure_ascii=True),
                    json.dumps(list(safe_actions), ensure_ascii=True),
                    1 if trusted_actions else 0,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM problem_events WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return _event_from_row(row) if row else None
    except (sqlite3.Error, TypeError, ValueError):
        return None


def list_problem_events(limit: int = 30) -> list[ProblemEvent]:
    safe_limit = min(max(int(limit), 1), 200)
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM problem_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise ProblemStoreError("Impossible de lire les evenements resolver.") from exc
    return [_event_from_row(row) for row in rows]


def problem_resolver_status(limit: int = 20) -> dict[str, Any]:
    events = list_problem_events(limit=limit)
    try:
        with _connect() as connection:
            total_row = connection.execute("SELECT COUNT(*) AS count FROM problem_events").fetchone()
            by_type_rows = connection.execute(
                """
                SELECT problem_type, COUNT(*) AS count
                FROM problem_events
                GROUP BY problem_type
                ORDER BY count DESC
                """
            ).fetchall()
    except sqlite3.Error as exc:
        raise ProblemStoreError("Impossible de lire le statut resolver.") from exc

    return {
        "enabled": True,
        "total": int(total_row["count"]) if total_row else 0,
        "recent": [problem_event_to_dict(event) for event in events],
        "by_type": {
            str(row["problem_type"]): int(row["count"])
            for row in by_type_rows
        },
        "policy": (
            "Eva ne termine pas sur un refus passif: elle journalise le blocage, "
            "essaie les routes alternatives sures, puis rend un diagnostic verifie."
        ),
    }


def _json_tuple(value: str) -> tuple[str, ...]:
    try:
        loaded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return ()
    if not isinstance(loaded, list):
        return ()
    return tuple(str(item) for item in loaded if str(item).strip())


def _event_from_row(row: sqlite3.Row) -> ProblemEvent:
    return ProblemEvent(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        message=str(row["message"]),
        domain=str(row["domain"]),
        expected_outcome=str(row["expected_outcome"]),
        problem_type=str(row["problem_type"]),
        summary=str(row["summary"]),
        tool=str(row["tool"]),
        status=str(row["status"]),
        error=str(row["error"]),
        alternate_routes=_json_tuple(str(row["alternate_routes"])),
        safe_actions=_json_tuple(str(row["safe_actions"])),
        trusted_actions=bool(row["trusted_actions"]),
    )


def problem_event_to_dict(event: ProblemEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "created_at": event.created_at,
        "message": event.message,
        "domain": event.domain,
        "expected_outcome": event.expected_outcome,
        "problem_type": event.problem_type,
        "summary": event.summary,
        "tool": event.tool,
        "status": event.status,
        "error": event.error,
        "alternate_routes": list(event.alternate_routes),
        "safe_actions": list(event.safe_actions),
        "trusted_actions": event.trusted_actions,
    }
