import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.agents.understanding import build_understanding_frame, understanding_to_dict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
OPERATOR_DB_PATH = DATA_DIR / "eva_operator_journal.sqlite"

OperatorStatus = Literal["completed", "needs_followup", "blocked", "failed"]


class OperatorJournalError(Exception):
    """Raised when Eva cannot record or read the local operator journal."""


@dataclass(frozen=True)
class OperatorTick:
    id: int
    created_at: str
    channel: str
    message: str
    response: str
    intent_name: str
    domain: str
    expected_outcome: str
    route: str
    tool_preference: str
    safety_level: str
    trusted_actions: bool
    status: OperatorStatus
    reflex_note: str


WEAK_RESPONSE_MARKERS = (
    "je suis une assistante virtuelle",
    "je ne peux pas ouvrir",
    "je ne peux pas interagir",
    "aucun resultat web exploitable",
    "aucune analyse exploitable",
    "impossible",
    "indisponible",
    "je n'ai pas pu",
    "je ne trouve pas",
)

ERROR_MARKERS = (
    "traceback",
    "commandnotfoundexception",
    "module not found",
    "modulenotfounderror",
    "err_connection_refused",
    "access_denied",
    "erreur",
)


def init_operator_journal() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(OPERATOR_DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    message TEXT NOT NULL,
                    response TEXT NOT NULL,
                    intent_name TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    expected_outcome TEXT NOT NULL,
                    route TEXT NOT NULL,
                    tool_preference TEXT NOT NULL,
                    safety_level TEXT NOT NULL,
                    trusted_actions INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reflex_note TEXT NOT NULL
                )
                """
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise OperatorJournalError("Impossible d'initialiser le journal operateur Eva.") from exc


def _connect() -> sqlite3.Connection:
    init_operator_journal()
    connection = sqlite3.connect(OPERATOR_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _infer_status(response: str) -> OperatorStatus:
    normalized = _normalize(response)
    if any(marker in normalized for marker in WEAK_RESPONSE_MARKERS):
        return "needs_followup"
    if any(marker in normalized for marker in ERROR_MARKERS):
        return "needs_followup"
    if "session non fiable" in normalized or "action locale refusee" in normalized:
        return "blocked"
    return "completed"


def _reflex_note(message: str, response: str, domain: str, route: str) -> str:
    combined = _normalize(f"{message}\n{response}")

    if "je suis une assistante virtuelle" in combined or "je ne peux pas ouvrir" in combined:
        return (
            "Reflexe: mauvaise posture sans outils. Repasser par la couche comprehension, "
            "puis tenter browser_assistant, desktop_automation ou screen_reader selon la demande."
        )

    if "aucun resultat web exploitable" in combined:
        return (
            "Reflexe: relancer la recherche avec une requete reformulee, puis ouvrir Brave "
            "sur la page de recherche si aucun extrait exploitable ne revient."
        )

    if any(marker in combined for marker in ("traceback", "commandnotfoundexception", "modulenotfounderror")):
        return (
            "Reflexe: traiter comme erreur terminal. Utiliser terminal_doctor ou screen_reader "
            "avec auto_fix si l'erreur est visible a l'ecran."
        )

    if domain == "gmail" and any(marker in combined for marker in ("j'ai prepare un brouillon", "mail source")):
        return "Reflexe: conserver le fil Gmail comme contexte pour les prochains follow-ups Telegram."

    if route in {"browser_or_video", "spotify", "desktop_control"}:
        return "Reflexe: action locale executee ou tentee. Verifier l'ecran si Victor signale que rien ne s'est ouvert."

    if domain == "project":
        return "Reflexe: suivre le workspace cree, les prompts Cursor et les erreurs Git/Cursor dans les prochains ticks."

    return "Reflexe: aucune relance automatique necessaire."


def _row_to_tick(row: sqlite3.Row) -> OperatorTick:
    return OperatorTick(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        channel=str(row["channel"]),
        message=str(row["message"]),
        response=str(row["response"]),
        intent_name=str(row["intent_name"]),
        domain=str(row["domain"]),
        expected_outcome=str(row["expected_outcome"]),
        route=str(row["route"]),
        tool_preference=str(row["tool_preference"]),
        safety_level=str(row["safety_level"]),
        trusted_actions=bool(row["trusted_actions"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        reflex_note=str(row["reflex_note"]),
    )


def record_operator_tick(
    message: str,
    response: str,
    *,
    channel: str,
    trusted_actions: bool,
    conversation_context: list[dict[str, str]] | None = None,
) -> OperatorTick:
    frame = build_understanding_frame(
        message,
        conversation_context=conversation_context or [],
        trusted_actions=trusted_actions,
    )
    frame_payload = understanding_to_dict(frame)
    action_plan = frame_payload["action_plan"]
    if not isinstance(action_plan, dict):
        action_plan = {}

    status = _infer_status(response)
    reflex_note = _reflex_note(
        message,
        response,
        str(frame_payload["primary_domain"]),
        str(action_plan.get("route", "")),
    )
    created_at = datetime.now(UTC).isoformat()

    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO operator_ticks (
                    created_at,
                    channel,
                    message,
                    response,
                    intent_name,
                    domain,
                    expected_outcome,
                    route,
                    tool_preference,
                    safety_level,
                    trusted_actions,
                    status,
                    reflex_note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    channel[:40],
                    message[:4000],
                    response[:8000],
                    str(frame_payload["intent"]["name"]) if isinstance(frame_payload["intent"], dict) else "",
                    str(frame_payload["primary_domain"]),
                    str(frame_payload["expected_outcome"]),
                    str(action_plan.get("route", "")),
                    str(frame_payload["tool_preference"]),
                    str(frame_payload["safety_level"]),
                    1 if trusted_actions else 0,
                    status,
                    reflex_note,
                ),
            )
            connection.commit()
            tick_id = int(cursor.lastrowid)
    except sqlite3.Error as exc:
        raise OperatorJournalError("Impossible d'enregistrer le tick operateur Eva.") from exc

    return OperatorTick(
        id=tick_id,
        created_at=created_at,
        channel=channel[:40],
        message=message[:4000],
        response=response[:8000],
        intent_name=str(frame_payload["intent"]["name"]) if isinstance(frame_payload["intent"], dict) else "",
        domain=str(frame_payload["primary_domain"]),
        expected_outcome=str(frame_payload["expected_outcome"]),
        route=str(action_plan.get("route", "")),
        tool_preference=str(frame_payload["tool_preference"]),
        safety_level=str(frame_payload["safety_level"]),
        trusted_actions=trusted_actions,
        status=status,
        reflex_note=reflex_note,
    )


def list_operator_ticks(limit: int = 50) -> list[OperatorTick]:
    safe_limit = min(max(limit, 1), 200)
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM operator_ticks
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise OperatorJournalError("Impossible de lire le journal operateur Eva.") from exc
    return [_row_to_tick(row) for row in rows]


def operator_tick_to_dict(tick: OperatorTick) -> dict[str, object]:
    return {
        "id": tick.id,
        "created_at": tick.created_at,
        "channel": tick.channel,
        "message": tick.message,
        "response": tick.response,
        "intent_name": tick.intent_name,
        "domain": tick.domain,
        "expected_outcome": tick.expected_outcome,
        "route": tick.route,
        "tool_preference": tick.tool_preference,
        "safety_level": tick.safety_level,
        "trusted_actions": tick.trusted_actions,
        "status": tick.status,
        "reflex_note": tick.reflex_note,
    }


def operator_status() -> dict[str, object]:
    init_operator_journal()
    try:
        with _connect() as connection:
            total = connection.execute("SELECT COUNT(*) AS count FROM operator_ticks").fetchone()
            needs_followup = connection.execute(
                "SELECT COUNT(*) AS count FROM operator_ticks WHERE status = 'needs_followup'"
            ).fetchone()
            latest = connection.execute(
                """
                SELECT *
                FROM operator_ticks
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error as exc:
        raise OperatorJournalError("Impossible de lire le statut operateur Eva.") from exc

    return {
        "db_path": str(OPERATOR_DB_PATH),
        "ticks": int(total["count"]) if total else 0,
        "needs_followup": int(needs_followup["count"]) if needs_followup else 0,
        "latest": operator_tick_to_dict(_row_to_tick(latest)) if latest else None,
    }
