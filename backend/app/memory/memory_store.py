import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MemoryStoreError(Exception):
    """Raised when Eva cannot safely read or write local memories."""


@dataclass(frozen=True)
class Memory:
    id: int
    content: str
    category: str
    created_at: str
    source: str
    confidence: float


@dataclass(frozen=True)
class MemoryCandidate:
    content: str
    category: str
    confidence: float


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
MEMORY_DB_PATH = DATA_DIR / "eva_memory.sqlite"

MAX_MEMORY_LENGTH = 600
MAX_PROMPT_MEMORIES = 20
DEFAULT_CATEGORY = "general"

FORBIDDEN_MEMORY_PATTERNS = (
    "password",
    "mot de passe",
    "passwd",
    "token",
    "api key",
    "api_key",
    "apikey",
    "secret",
    "cle secrete",
)

REMEMBER_PATTERNS = (
    r"^\s*(?:eva[, ]*)?(?:retiens|souviens-toi|souviens toi|note|memorise|m.morise)(?:\s+que)?\s*:?\s*(?P<content>.+)$",
    r"^\s*(?:remember|save|note)(?:\s+that)?\s*:?\s*(?P<content>.+)$",
)


def init_memory_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(MEMORY_DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'explicit',
                    confidence REAL NOT NULL DEFAULT 1.0
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(memories)").fetchall()
            }
            if "source" not in columns:
                connection.execute(
                    "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'explicit'"
                )
            if "confidence" not in columns:
                connection.execute(
                    "ALTER TABLE memories ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0"
                )
            connection.commit()
    except sqlite3.Error as exc:
        raise MemoryStoreError("Impossible d'initialiser la memoire locale Eva.") from exc


def _connect() -> sqlite3.Connection:
    init_memory_store()
    connection = sqlite3.connect(MEMORY_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _normalize_for_detection(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.lower().strip().split())


def _contains_forbidden_secret(content: str) -> bool:
    normalized = _normalize_for_detection(content)
    return any(pattern in normalized for pattern in FORBIDDEN_MEMORY_PATTERNS)


def sanitize_memory_content(content: str) -> str:
    cleaned = " ".join(content.strip().split())

    if not cleaned:
        raise MemoryStoreError("La memoire a enregistrer est vide.")

    if len(cleaned) > MAX_MEMORY_LENGTH:
        raise MemoryStoreError(
            f"La memoire est trop longue. Maximum: {MAX_MEMORY_LENGTH} caracteres."
        )

    if _contains_forbidden_secret(cleaned):
        raise MemoryStoreError(
            "Eva ne doit pas stocker de mots de passe, tokens, cles API ou secrets."
        )

    return cleaned


def add_memory(
    content: str,
    category: str = DEFAULT_CATEGORY,
    source: str = "explicit",
    confidence: float = 1.0,
) -> Memory:
    cleaned_content = sanitize_memory_content(content)
    cleaned_category = re.sub(r"[^a-zA-Z0-9_-]", "", category.strip()) or DEFAULT_CATEGORY
    cleaned_source = re.sub(r"[^a-zA-Z0-9_-]", "", source.strip()) or "explicit"
    safe_confidence = min(max(float(confidence), 0.0), 1.0)
    created_at = datetime.now(UTC).isoformat()

    try:
        with _connect() as connection:
            existing = connection.execute(
                """
                SELECT id, content, category, created_at, source, confidence
                FROM memories
                WHERE lower(content) = lower(?)
                LIMIT 1
                """,
                (cleaned_content,),
            ).fetchone()
            if existing:
                return Memory(
                    id=int(existing["id"]),
                    content=str(existing["content"]),
                    category=str(existing["category"]),
                    created_at=str(existing["created_at"]),
                    source=str(existing["source"]),
                    confidence=float(existing["confidence"]),
                )

            cursor = connection.execute(
                """
                INSERT INTO memories (content, category, created_at, source, confidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cleaned_content,
                    cleaned_category,
                    created_at,
                    cleaned_source,
                    safe_confidence,
                ),
            )
            connection.commit()
            memory_id = int(cursor.lastrowid)
    except sqlite3.Error as exc:
        raise MemoryStoreError("Impossible d'enregistrer la memoire locale.") from exc

    return Memory(
        id=memory_id,
        content=cleaned_content,
        category=cleaned_category,
        created_at=created_at,
        source=cleaned_source,
        confidence=safe_confidence,
    )


def list_memories(limit: int = 50) -> list[Memory]:
    safe_limit = min(max(limit, 1), 200)

    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content, category, created_at, source, confidence
                FROM memories
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise MemoryStoreError("Impossible de lire la memoire locale.") from exc

    return [
        Memory(
            id=int(row["id"]),
            content=str(row["content"]),
            category=str(row["category"]),
            created_at=str(row["created_at"]),
            source=str(row["source"]),
            confidence=float(row["confidence"]),
        )
        for row in rows
    ]


def delete_memory(memory_id: int) -> bool:
    try:
        with _connect() as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            connection.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        raise MemoryStoreError("Impossible de supprimer cette memoire locale.") from exc


def detect_explicit_memory_request(message: str) -> str | None:
    for pattern in REMEMBER_PATTERNS:
        match = re.match(pattern, message, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return sanitize_memory_content(match.group("content"))

    return None


def detect_auto_memory_candidate(message: str) -> MemoryCandidate | None:
    cleaned = sanitize_memory_content(message)
    normalized = _normalize_for_detection(cleaned)

    if len(cleaned) < 12 or len(cleaned) > 260:
        return None

    if "?" in cleaned:
        return None

    blocked_starts = (
        "peux tu",
        "peux-tu",
        "est ce que",
        "resume",
        "resumes",
        "lis ",
        "lire ",
        "analyse ",
        "corrige ",
        "ecris ",
        "redige ",
        "cree ",
        "fais ",
    )
    if normalized.startswith(blocked_starts):
        return None

    identity_markers = (
        "je m'appelle",
        "mon nom est",
        "mon email est",
        "mon adresse email est",
    )
    if any(marker in normalized for marker in identity_markers):
        return MemoryCandidate(content=cleaned, category="identity", confidence=0.92)

    preference_markers = (
        "je prefere",
        "je n'aime pas",
        "j'aime",
        "je deteste",
        "je veux que tu",
        "je voudrais que tu",
        "a partir de maintenant",
        "mon style prefere",
    )
    if any(marker in normalized for marker in preference_markers):
        return MemoryCandidate(content=cleaned, category="preference", confidence=0.86)

    goal_markers = (
        "mon objectif est",
        "mon but est",
        "je veux atteindre",
        "ma priorite est",
        "ma priorite du moment",
    )
    if any(marker in normalized for marker in goal_markers):
        return MemoryCandidate(content=cleaned, category="goal", confidence=0.84)

    project_markers = (
        "je travaille sur",
        "mon projet",
        "dreamlense",
        "eva doit",
        "eva devra",
    )
    if any(marker in normalized for marker in project_markers):
        return MemoryCandidate(content=cleaned, category="project", confidence=0.78)

    return None


def memory_to_dict(memory: Memory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "content": memory.content,
        "category": memory.category,
        "created_at": memory.created_at,
        "source": memory.source,
        "confidence": memory.confidence,
    }


def build_memory_prompt_context() -> str:
    memories = list_memories(limit=MAX_PROMPT_MEMORIES)

    if not memories:
        return (
            "Memoire locale: aucune memoire utilisateur n'est encore enregistree. "
            "N'invente pas de souvenirs."
        )

    lines = [
        "Memoires locales explicites ou detectees avec prudence pour Victor.",
        "Utilise ces informations quand elles sont utiles, sans inventer d'autres souvenirs.",
    ]

    for memory in reversed(memories):
        lines.append(f"- [{memory.category}/{memory.source}] {memory.content}")

    return "\n".join(lines)
