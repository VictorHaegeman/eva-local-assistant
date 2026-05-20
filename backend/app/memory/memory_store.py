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


@dataclass(frozen=True)
class MemorySearchResult:
    memory: Memory
    score: float


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

NEGATIVE_MEMORY_MARKERS = (
    "ne retiens pas",
    "ne memorise pas",
    "ne mets pas dans la memoire",
    "ne met pas dans la memoire",
    "n'enregistre pas",
)

ASSISTANT_META_MEMORY_MARKERS = (
    "je veux que eva",
    "fais en sorte que eva",
    "eva doit",
    "eva devra",
    "eva puisse",
    "qu'eva",
    "qu eva",
    "l'assistante",
    "assistant local",
)

ASSISTANT_META_TOPICS = (
    "prompt",
    "interprete",
    "interpreter",
    "comprenne",
    "comprendre",
    "avant d'agir",
    "avant d agir",
    "action",
    "actions",
    "outil",
    "outils",
    "autonome",
    "autonomie",
    "execute",
    "executer",
    "reponde",
    "repondre",
    "memoire",
    "telegram",
    "gmail",
    "cursor",
    "codex",
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
            _ensure_memory_fts(connection)
            connection.commit()
    except sqlite3.Error as exc:
        raise MemoryStoreError("Impossible d'initialiser la memoire locale Eva.") from exc


def _ensure_memory_fts(connection: sqlite3.Connection) -> None:
    try:
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(
                content,
                category,
                source,
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO memories_fts(rowid, content, category, source)
            SELECT id, content, category, source
            FROM memories
            """
        )
    except sqlite3.Error:
        # Some SQLite builds may not expose FTS5. Eva keeps the normal memory table
        # and falls back to LIKE search when retrieval is requested.
        return


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


def _is_negative_memory_request(normalized: str) -> bool:
    return any(marker in normalized for marker in NEGATIVE_MEMORY_MARKERS)


def _is_assistant_meta_instruction(normalized: str) -> bool:
    if any(marker in normalized for marker in ASSISTANT_META_MEMORY_MARKERS):
        return True

    mentions_eva = "eva" in normalized
    mentions_meta_topic = any(topic in normalized for topic in ASSISTANT_META_TOPICS)
    return mentions_eva and mentions_meta_topic


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
            try:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO memories_fts(rowid, content, category, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (cursor.lastrowid, cleaned_content, cleaned_category, cleaned_source),
                )
            except sqlite3.Error:
                pass
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
            try:
                connection.execute("DELETE FROM memories_fts WHERE rowid = ?", (memory_id,))
            except sqlite3.Error:
                pass
            connection.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        raise MemoryStoreError("Impossible de supprimer cette memoire locale.") from exc


def detect_explicit_memory_request(message: str) -> str | None:
    normalized = _normalize_for_detection(message)
    if _is_negative_memory_request(normalized):
        return None

    for pattern in REMEMBER_PATTERNS:
        match = re.match(pattern, message, flags=re.IGNORECASE | re.DOTALL)
        if match:
            content = sanitize_memory_content(match.group("content"))
            if _is_assistant_meta_instruction(_normalize_for_detection(content)):
                return None
            return content

    return None


def detect_auto_memory_candidate(message: str) -> MemoryCandidate | None:
    raw_normalized = _normalize_for_detection(message)
    if _is_negative_memory_request(raw_normalized) or _is_assistant_meta_instruction(raw_normalized):
        return None

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
    )
    if any(marker in normalized for marker in project_markers):
        return MemoryCandidate(content=cleaned, category="project", confidence=0.78)

    return None


def detect_operating_lesson_candidate(message: str) -> MemoryCandidate | None:
    raw_normalized = _normalize_for_detection(message)
    if _is_negative_memory_request(raw_normalized):
        return None

    mentions_eva = "eva" in raw_normalized
    mentions_correction = any(
        marker in raw_normalized
        for marker in (
            "je veux que",
            "fais en sorte",
            "il faut que",
            "elle doit",
            "eva doit",
            "eva puisse",
            "ca ne marche pas",
            "ça ne marche pas",
            "elle ne reflechit pas",
            "elle ne réfléchit pas",
            "avant d'agir",
            "avant d agir",
        )
    )
    if not (mentions_eva and mentions_correction):
        return None

    lessons: list[str] = []
    if any(marker in raw_normalized for marker in ("interprete", "interpreter", "comprenne", "comprendre", "reflechit", "reflechir")):
        lessons.append(
            "Avant une action, Eva doit interpreter l'objectif reel, identifier le contexte utile, choisir l'outil adapte, puis executer une etape verifiable."
        )

    if any(marker in raw_normalized for marker in ("coordonnees", "coordonnées", "ou cliquer", "bouton")):
        lessons.append(
            "Pour une action UI sans coordonnees, Eva doit utiliser la vision d'ecran pour trouver le bouton ou champ par son libelle et sa position probable."
        )

    if any(marker in raw_normalized for marker in ("memoire", "apprenne", "apprendre", "retienne", "retenir")):
        lessons.append(
            "Eva doit transformer les corrections de Victor en regles courtes et reutilisables, sans stocker les phrases brutes ni les secrets."
        )

    if any(marker in raw_normalized for marker in ("mail", "gmail", "beeper", "message")):
        lessons.append(
            "Pour les mails et messages, Eva doit lire le contenu pertinent avant d'ouvrir des liens ou de preparer une reponse."
        )

    if not lessons:
        return None

    content = " ".join(dict.fromkeys(lessons))
    return MemoryCandidate(content=content, category="operating_rule", confidence=0.9)


def memory_to_dict(memory: Memory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "content": memory.content,
        "category": memory.category,
        "created_at": memory.created_at,
        "source": memory.source,
        "confidence": memory.confidence,
    }


def _fts_query_from_text(query: str) -> str:
    normalized = _normalize_for_detection(query)
    tokens = re.findall(r"[a-zA-Z0-9_]{3,}", normalized)
    stopwords = {
        "avec",
        "dans",
        "pour",
        "que",
        "qui",
        "quoi",
        "sur",
        "les",
        "des",
        "mes",
        "mon",
        "une",
        "un",
        "est",
        "suis",
        "eva",
    }
    unique_tokens = []
    for token in tokens:
        if token in stopwords or token in unique_tokens:
            continue
        unique_tokens.append(token)
    return " OR ".join(f"{token}*" for token in unique_tokens[:12])


def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=int(row["id"]),
        content=str(row["content"]),
        category=str(row["category"]),
        created_at=str(row["created_at"]),
        source=str(row["source"]),
        confidence=float(row["confidence"]),
    )


def search_memories(query: str, limit: int = 8) -> list[MemorySearchResult]:
    safe_limit = min(max(limit, 1), 20)
    fts_query = _fts_query_from_text(query)
    if not fts_query:
        return []

    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    m.id,
                    m.content,
                    m.category,
                    m.created_at,
                    m.source,
                    m.confidence,
                    bm25(memories_fts) AS score
                FROM memories_fts
                JOIN memories AS m ON m.id = memories_fts.rowid
                WHERE memories_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, safe_limit),
            ).fetchall()
            return [
                MemorySearchResult(memory=_row_to_memory(row), score=float(row["score"]))
                for row in rows
            ]
    except sqlite3.Error:
        pass

    normalized_tokens = [
        token.rstrip("*")
        for token in fts_query.split(" OR ")
        if token.rstrip("*")
    ]
    if not normalized_tokens:
        return []

    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content, category, created_at, source, confidence
                FROM memories
                ORDER BY id DESC
                LIMIT 200
                """
            ).fetchall()
    except sqlite3.Error as exc:
        raise MemoryStoreError("Impossible de rechercher dans la memoire locale.") from exc

    results: list[MemorySearchResult] = []
    for row in rows:
        memory = _row_to_memory(row)
        haystack = _normalize_for_detection(f"{memory.content} {memory.category} {memory.source}")
        matches = sum(1 for token in normalized_tokens if token in haystack)
        if matches:
            results.append(MemorySearchResult(memory=memory, score=float(-matches)))

    return sorted(results, key=lambda result: result.score)[:safe_limit]


def build_relevant_memory_prompt_context(query: str) -> str:
    results = search_memories(query, limit=8)
    if not results:
        return (
            "Memoires pertinentes pour la demande actuelle: aucune memoire locale "
            "specifique trouvee. N'invente pas de souvenirs."
        )

    lines = [
        "Memoires pertinentes retrouvees par SQLite FTS5/BM25 local.",
        "Utilise-les seulement si elles aident la demande actuelle.",
    ]
    for result in results:
        memory = result.memory
        lines.append(f"- [{memory.category}/{memory.source}] {memory.content}")
    return "\n".join(lines)


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
