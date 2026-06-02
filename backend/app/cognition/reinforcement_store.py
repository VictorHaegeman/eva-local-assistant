import json
import math
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings


class ReinforcementStoreError(Exception):
    """Raised when Eva cannot store or read local reinforcement signals."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
REINFORCEMENT_DB_PATH = DATA_DIR / "eva_reinforcement.sqlite"

POSITIVE_FEEDBACK_MARKERS = (
    "c'est bien",
    "c est bien",
    "nickel",
    "parfait",
    "top",
    "ça marche",
    "ca marche",
    "bien joue",
    "bien joué",
    "exactement",
)

NEGATIVE_FEEDBACK_MARKERS = (
    "c'est pas normal",
    "c est pas normal",
    "aucun sens",
    "ca n'a aucun sens",
    "c est n importe quoi",
    "comprend rien",
    "comprends rien",
    "comprend plus",
    "comprends plus",
    "elle comprend rien",
    "elle comprends rien",
    "elle comprend plus",
    "elle comprends plus",
    "elle interprete plus",
    "elle n'interprete plus",
    "elle ne reflechit pas",
    "elle reflechit pas",
    "ne reflechis pas",
    "pas assez reflechissant",
    "hors sujet",
    "repart dans du hors sujet",
    "part dans du hors sujet",
    "pas ce que",
    "ça ne marche pas",
    "ca ne marche pas",
    "ne marche pas",
    "elle a rien fait",
    "elle n'a rien fait",
    "elle ne fait rien",
    "trop bete",
    "pas satisfait",
    "je suis pas satisfait",
    "j'suis pas satisfait",
    "mauvaise route",
    "mauvais outil",
    "mauvaise interpretation",
    "mauvaise interprétation",
)

MISROUTE_MARKERS = (
    "recherche web gratuite",
    "je ne peux pas ouvrir",
    "je suis une assistante virtuelle",
    "il me manque le projet cible",
    "aucun resultat web exploitable",
)


@dataclass(frozen=True)
class RewardEvent:
    id: int
    created_at: str
    state_key: str
    action_key: str
    reward: float
    source: str
    reason: str
    status: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ActionRewardStats:
    state_key: str
    action_key: str
    attempts: int
    success_count: int
    penalty_count: int
    total_reward: float
    avg_reward: float
    policy_score: float
    last_reward: float
    updated_at: str


@dataclass(frozen=True)
class RouteRecommendation:
    state_key: str
    current_action: str
    selected_action: str
    should_switch: bool
    current_score: float
    selected_score: float
    summary: str
    candidates: tuple[ActionRewardStats, ...]


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", str(text or "").lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _safe_key(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9:_-]+", "_", str(value or "").strip()).strip("_")
    return cleaned[:120] or fallback


def init_reinforcement_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(REINFORCEMENT_DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reward_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    state_key TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    reward REAL NOT NULL,
                    source TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS action_reward_stats (
                    state_key TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    penalty_count INTEGER NOT NULL DEFAULT 0,
                    total_reward REAL NOT NULL DEFAULT 0,
                    avg_reward REAL NOT NULL DEFAULT 0,
                    policy_score REAL NOT NULL DEFAULT 0,
                    last_reward REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (state_key, action_key)
                )
                """
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ReinforcementStoreError("Impossible d'initialiser le reward store Eva.") from exc


def _connect() -> sqlite3.Connection:
    init_reinforcement_store()
    connection = sqlite3.connect(REINFORCEMENT_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _policy_score(avg_reward: float, attempts: int, total_state_attempts: int) -> float:
    if attempts <= 0:
        return 0.0
    exploration_bonus = settings.eva_reinforcement_exploration_bonus * math.sqrt(
        math.log(max(total_state_attempts, 2)) / attempts
    )
    confidence_penalty = 0.08 / max(attempts, 1)
    return avg_reward + exploration_bonus - confidence_penalty


def _recompute_state_scores(connection: sqlite3.Connection, state_key: str) -> None:
    rows = connection.execute(
        """
        SELECT action_key, attempts, avg_reward
        FROM action_reward_stats
        WHERE state_key = ?
        """,
        (state_key,),
    ).fetchall()
    total_attempts = sum(int(row["attempts"]) for row in rows) or 1
    for row in rows:
        attempts = int(row["attempts"])
        avg_reward = float(row["avg_reward"])
        connection.execute(
            """
            UPDATE action_reward_stats
            SET policy_score = ?
            WHERE state_key = ? AND action_key = ?
            """,
            (_policy_score(avg_reward, attempts, total_attempts), state_key, str(row["action_key"])),
        )


def record_reward_event(
    *,
    state_key: str,
    action_key: str,
    reward: float,
    source: str,
    reason: str,
    status: str = "",
    metadata: dict[str, Any] | None = None,
) -> RewardEvent:
    if not settings.eva_reinforcement_enabled:
        raise ReinforcementStoreError("Le reinforcement local Eva est desactive.")

    safe_state = _safe_key(state_key, "chat:answer")
    safe_action = _safe_key(action_key, "generic_chat")
    safe_reward = min(max(float(reward), -1.5), 1.5)
    created_at = datetime.now(UTC).isoformat()
    safe_source = _safe_key(source, "system")[:60]
    safe_reason = " ".join(str(reason or "reward").split())[:240]
    safe_status = _safe_key(status, "unknown")[:80]
    metadata_json = json.dumps(metadata or {}, ensure_ascii=True, separators=(",", ":"))

    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO reward_events (
                    created_at, state_key, action_key, reward, source, reason, status, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    safe_state,
                    safe_action,
                    safe_reward,
                    safe_source,
                    safe_reason,
                    safe_status,
                    metadata_json,
                ),
            )
            row = connection.execute(
                """
                SELECT attempts, success_count, penalty_count, total_reward
                FROM action_reward_stats
                WHERE state_key = ? AND action_key = ?
                """,
                (safe_state, safe_action),
            ).fetchone()
            attempts = int(row["attempts"]) + 1 if row else 1
            success_count = int(row["success_count"]) + (1 if safe_reward > 0.25 else 0) if row else (1 if safe_reward > 0.25 else 0)
            penalty_count = int(row["penalty_count"]) + (1 if safe_reward < -0.2 else 0) if row else (1 if safe_reward < -0.2 else 0)
            total_reward = float(row["total_reward"]) + safe_reward if row else safe_reward
            avg_reward = total_reward / max(attempts, 1)
            connection.execute(
                """
                INSERT OR REPLACE INTO action_reward_stats (
                    state_key,
                    action_key,
                    attempts,
                    success_count,
                    penalty_count,
                    total_reward,
                    avg_reward,
                    policy_score,
                    last_reward,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_state,
                    safe_action,
                    attempts,
                    success_count,
                    penalty_count,
                    total_reward,
                    avg_reward,
                    _policy_score(avg_reward, attempts, attempts),
                    safe_reward,
                    created_at,
                ),
            )
            _recompute_state_scores(connection, safe_state)
            connection.commit()
            event_id = int(cursor.lastrowid)
    except sqlite3.Error as exc:
        raise ReinforcementStoreError("Impossible d'enregistrer la recompense locale.") from exc

    return RewardEvent(
        id=event_id,
        created_at=created_at,
        state_key=safe_state,
        action_key=safe_action,
        reward=safe_reward,
        source=safe_source,
        reason=safe_reason,
        status=safe_status,
        metadata=metadata or {},
    )


def reward_from_tick_fields(
    *,
    status: str,
    message: str,
    response: str,
    domain: str,
    route: str,
) -> tuple[float, str]:
    normalized_message = _normalize(message)
    normalized_response = _normalize(response)
    combined = f"{normalized_message} {normalized_response}"
    safe_status = _normalize(status)

    if safe_status == "completed":
        reward = 0.75
        reason = "completed"
    elif safe_status == "needs_followup":
        reward = -0.45
        reason = "needs_followup"
    elif safe_status == "blocked":
        reward = -0.65
        reason = "blocked"
    elif safe_status == "failed":
        reward = -0.9
        reason = "failed"
    else:
        reward = 0.0
        reason = "unknown_status"

    if any(marker in normalized_message for marker in POSITIVE_FEEDBACK_MARKERS):
        reward += 0.45
        reason = f"{reason}+positive_feedback"
    if any(marker in normalized_message for marker in NEGATIVE_FEEDBACK_MARKERS):
        reward -= 0.65
        reason = f"{reason}+negative_feedback"
    if any(marker in normalized_response for marker in MISROUTE_MARKERS):
        reward -= 0.35
        reason = f"{reason}+misroute_marker"
    if "recherche web gratuite" in normalized_response and domain in {"gmail", "calendar", "desktop", "cursor"}:
        reward -= 0.45
        reason = f"{reason}+wrong_web_fallback"
    if "invalid_grant" in combined and domain == "gmail":
        reward -= 0.2
        reason = f"{reason}+oauth_reconnect_needed"
    if route in {"gmail_read", "gmail_reply_audit", "gmail_reply_draft"} and "gmail api" in normalized_response:
        reward += 0.15
        reason = f"{reason}+expected_tool"

    return min(max(reward, -1.5), 1.5), reason


def feedback_reward_from_message(message: str) -> tuple[float, str] | None:
    normalized_message = _normalize(message)
    if any(marker in normalized_message for marker in POSITIVE_FEEDBACK_MARKERS):
        return 1.0, "explicit_positive_feedback"
    if any(marker in normalized_message for marker in NEGATIVE_FEEDBACK_MARKERS):
        return -1.0, "explicit_negative_feedback"
    return None


def record_feedback_for_tick(
    tick: Any,
    feedback_message: str,
    *,
    source: str = "user_feedback_previous_tick",
) -> RewardEvent | None:
    parsed = feedback_reward_from_message(feedback_message)
    if parsed is None or not settings.eva_reinforcement_enabled:
        return None

    reward, reason = parsed
    domain = str(getattr(tick, "domain", "chat") or "chat")
    outcome = str(getattr(tick, "expected_outcome", "answer") or "answer")
    route = str(getattr(tick, "route", "") or getattr(tick, "tool_preference", "") or "generic_chat")
    try:
        return record_reward_event(
            state_key=f"{domain}:{outcome}",
            action_key=route,
            reward=reward,
            source=source,
            reason=reason,
            status="feedback",
            metadata={
                "tick_id": getattr(tick, "id", None),
                "feedback": feedback_message[:500],
                "original_message": str(getattr(tick, "message", ""))[:500],
            },
        )
    except ReinforcementStoreError:
        return None


def record_tick_reward(tick: Any) -> RewardEvent | None:
    if not settings.eva_reinforcement_enabled:
        return None

    domain = str(getattr(tick, "domain", "chat") or "chat")
    outcome = str(getattr(tick, "expected_outcome", "answer") or "answer")
    route = str(getattr(tick, "route", "") or getattr(tick, "tool_preference", "") or "generic_chat")
    reward, reason = reward_from_tick_fields(
        status=str(getattr(tick, "status", "unknown")),
        message=str(getattr(tick, "message", "")),
        response=str(getattr(tick, "response", "")),
        domain=domain,
        route=route,
    )

    try:
        return record_reward_event(
            state_key=f"{domain}:{outcome}",
            action_key=route,
            reward=reward,
            source="operator_tick",
            reason=reason,
            status=str(getattr(tick, "status", "")),
            metadata={
                "tick_id": getattr(tick, "id", None),
                "domain": domain,
                "expected_outcome": outcome,
                "tool_preference": getattr(tick, "tool_preference", ""),
                "channel": getattr(tick, "channel", ""),
            },
        )
    except ReinforcementStoreError:
        return None


def _row_to_stats(row: sqlite3.Row) -> ActionRewardStats:
    return ActionRewardStats(
        state_key=str(row["state_key"]),
        action_key=str(row["action_key"]),
        attempts=int(row["attempts"]),
        success_count=int(row["success_count"]),
        penalty_count=int(row["penalty_count"]),
        total_reward=float(row["total_reward"]),
        avg_reward=float(row["avg_reward"]),
        policy_score=float(row["policy_score"]),
        last_reward=float(row["last_reward"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_event(row: sqlite3.Row) -> RewardEvent:
    try:
        metadata = json.loads(str(row["metadata_json"]))
    except json.JSONDecodeError:
        metadata = {}
    return RewardEvent(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        state_key=str(row["state_key"]),
        action_key=str(row["action_key"]),
        reward=float(row["reward"]),
        source=str(row["source"]),
        reason=str(row["reason"]),
        status=str(row["status"]),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def list_reward_stats(state_key: str = "", limit: int = 30) -> list[ActionRewardStats]:
    safe_limit = min(max(int(limit), 1), 200)
    try:
        with _connect() as connection:
            if state_key:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM action_reward_stats
                    WHERE state_key = ?
                    ORDER BY policy_score DESC, attempts DESC
                    LIMIT ?
                    """,
                    (_safe_key(state_key), safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM action_reward_stats
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
    except sqlite3.Error as exc:
        raise ReinforcementStoreError("Impossible de lire les scores reinforcement.") from exc
    return [_row_to_stats(row) for row in rows]


def list_reward_events(limit: int = 30) -> list[RewardEvent]:
    safe_limit = min(max(int(limit), 1), 200)
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM reward_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise ReinforcementStoreError("Impossible de lire les recompenses locales.") from exc
    return [_row_to_event(row) for row in rows]


def recommend_route_for_state(state_key: str, current_action: str) -> RouteRecommendation:
    safe_state = _safe_key(state_key)
    safe_current = _safe_key(current_action, "generic_chat")
    candidates = tuple(list_reward_stats(safe_state, limit=12))
    current_score = 0.0
    selected = safe_current
    selected_score = 0.0
    should_switch = False

    if candidates:
        current_stats = next((stats for stats in candidates if stats.action_key == safe_current), None)
        best = candidates[0]
        current_score = current_stats.policy_score if current_stats else 0.0
        selected = best.action_key
        selected_score = best.policy_score
        current_avg = current_stats.avg_reward if current_stats else 0.0
        current_attempts = current_stats.attempts if current_stats else 0
        score_delta = selected_score - current_score
        should_switch = (
            selected != safe_current
            and best.attempts >= settings.eva_reinforcement_min_attempts
            and best.avg_reward >= 0.25
            and current_attempts >= 2
            and current_avg <= -0.15
            and score_delta >= settings.eva_reinforcement_switch_threshold
        )

    if should_switch:
        summary = f"Reward policy: route {safe_current} penalisee, {selected} favorisee sur {safe_state}."
    elif candidates:
        summary = f"Reward policy: {safe_current} conservee pour {safe_state}."
    else:
        summary = f"Reward policy: pas encore assez de donnees pour {safe_state}."

    return RouteRecommendation(
        state_key=safe_state,
        current_action=safe_current,
        selected_action=selected,
        should_switch=should_switch,
        current_score=current_score,
        selected_score=selected_score,
        summary=summary,
        candidates=candidates,
    )


def stats_to_dict(stats: ActionRewardStats) -> dict[str, object]:
    return {
        "state_key": stats.state_key,
        "action_key": stats.action_key,
        "attempts": stats.attempts,
        "success_count": stats.success_count,
        "penalty_count": stats.penalty_count,
        "total_reward": round(stats.total_reward, 4),
        "avg_reward": round(stats.avg_reward, 4),
        "policy_score": round(stats.policy_score, 4),
        "last_reward": round(stats.last_reward, 4),
        "updated_at": stats.updated_at,
    }


def event_to_dict(event: RewardEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "created_at": event.created_at,
        "state_key": event.state_key,
        "action_key": event.action_key,
        "reward": round(event.reward, 4),
        "source": event.source,
        "reason": event.reason,
        "status": event.status,
        "metadata": event.metadata,
    }


def reinforcement_status(limit: int = 30) -> dict[str, object]:
    if not settings.eva_reinforcement_enabled:
        return {
            "enabled": False,
            "db_path": str(REINFORCEMENT_DB_PATH),
            "message": "Reinforcement local desactive.",
        }

    init_reinforcement_store()
    try:
        with _connect() as connection:
            total = connection.execute("SELECT COUNT(*) AS count FROM reward_events").fetchone()
            positive = connection.execute("SELECT COUNT(*) AS count FROM reward_events WHERE reward > 0").fetchone()
            negative = connection.execute("SELECT COUNT(*) AS count FROM reward_events WHERE reward < 0").fetchone()
            avg = connection.execute("SELECT AVG(reward) AS avg_reward FROM reward_events").fetchone()
            states = connection.execute(
                """
                SELECT state_key, COUNT(*) AS actions
                FROM action_reward_stats
                GROUP BY state_key
                ORDER BY MAX(updated_at) DESC
                LIMIT 12
                """
            ).fetchall()
    except sqlite3.Error as exc:
        raise ReinforcementStoreError("Impossible de lire le statut reinforcement.") from exc

    stats = list_reward_stats(limit=limit)
    events = list_reward_events(limit=min(limit, 20))
    return {
        "enabled": True,
        "db_path": str(REINFORCEMENT_DB_PATH),
        "events": int(total["count"]) if total else 0,
        "positive": int(positive["count"]) if positive else 0,
        "negative": int(negative["count"]) if negative else 0,
        "avg_reward": round(float(avg["avg_reward"] or 0.0), 4) if avg else 0.0,
        "switch_threshold": settings.eva_reinforcement_switch_threshold,
        "min_attempts": settings.eva_reinforcement_min_attempts,
        "exploration_bonus": settings.eva_reinforcement_exploration_bonus,
        "states": [
            {
                "state_key": str(row["state_key"]),
                "actions": int(row["actions"]),
            }
            for row in states
        ],
        "stats": [stats_to_dict(item) for item in stats],
        "recent_events": [event_to_dict(event) for event in events],
    }
