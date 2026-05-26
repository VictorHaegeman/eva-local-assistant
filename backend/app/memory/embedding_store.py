import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.config import settings
from app.memory.cluster_store import infer_memory_cluster
from app.memory.memory_store import MEMORY_DB_PATH, Memory, list_memories, memory_to_dict


class EmbeddingStoreError(Exception):
    """Raised when Eva cannot read or write local memory embeddings."""


class EmbeddingUnavailableError(EmbeddingStoreError):
    """Raised when Ollama embeddings are disabled or unavailable."""


@dataclass(frozen=True)
class VectorMemoryResult:
    memory: Memory
    similarity: float
    cluster_key: str


def _connect() -> sqlite3.Connection:
    MEMORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(MEMORY_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_embedding_store() -> None:
    try:
        with _connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id INTEGER PRIMARY KEY,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    embedding_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    cluster_key TEXT NOT NULL DEFAULT 'general',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(memory_embeddings)").fetchall()
            }
            if "cluster_key" not in columns:
                connection.execute(
                    "ALTER TABLE memory_embeddings ADD COLUMN cluster_key TEXT NOT NULL DEFAULT 'general'"
                )
            _delete_orphan_embeddings(connection)
            connection.commit()
    except sqlite3.Error as exc:
        raise EmbeddingStoreError("Impossible d'initialiser la memoire vectorielle.") from exc


def _delete_orphan_embeddings(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        DELETE FROM memory_embeddings
        WHERE memory_id NOT IN (
            SELECT id
            FROM memories
        )
        """
    )


def _content_hash(memory: Memory) -> str:
    payload = json.dumps(memory_to_dict(memory), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_vector(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude <= 0:
        return vector
    return [value / magnitude for value in vector]


def _embedding_from_payload(payload: object) -> list[float]:
    if not isinstance(payload, dict):
        raise EmbeddingUnavailableError("Ollama a renvoye une reponse embedding inattendue.")

    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        first = embeddings[0]
        if isinstance(first, list):
            return [float(value) for value in first]

    embedding = payload.get("embedding")
    if isinstance(embedding, list):
        return [float(value) for value in embedding]

    raise EmbeddingUnavailableError("Ollama n'a pas renvoye d'embedding exploitable.")


def embed_text(text: str) -> list[float]:
    if not settings.eva_embeddings_enabled:
        raise EmbeddingUnavailableError("Memoire vectorielle desactivee.")

    clean_text = " ".join(text.strip().split())
    if not clean_text:
        raise EmbeddingUnavailableError("Texte vide pour embedding.")

    try:
        with httpx.Client(
            base_url=settings.ollama_base_url,
            timeout=settings.eva_embedding_timeout_seconds,
        ) as client:
            response = client.post(
                "/api/embed",
                json={"model": settings.eva_embedding_model, "input": clean_text},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] if exc.response is not None else ""
        raise EmbeddingUnavailableError(
            f"Modele embedding Ollama indisponible: {settings.eva_embedding_model}. "
            f"Lance: ollama pull {settings.eva_embedding_model}. {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise EmbeddingUnavailableError("Impossible de contacter Ollama pour les embeddings.") from exc
    except ValueError as exc:
        raise EmbeddingUnavailableError("Ollama a renvoye une reponse embedding non JSON.") from exc

    return _normalize_vector(_embedding_from_payload(payload))


def _memory_embedding_text(memory: Memory) -> str:
    return (
        f"Categorie: {memory.category}\n"
        f"Source: {memory.source}\n"
        f"Souvenir: {memory.content}"
    )


def get_or_create_memory_embedding(memory: Memory) -> list[float]:
    init_embedding_store()
    content_hash = _content_hash(memory)

    try:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT embedding_json
                FROM memory_embeddings
                WHERE memory_id = ? AND model = ? AND content_hash = ?
                LIMIT 1
                """,
                (memory.id, settings.eva_embedding_model, content_hash),
            ).fetchone()
            if row:
                return [float(value) for value in json.loads(str(row["embedding_json"]))]
    except (sqlite3.Error, json.JSONDecodeError) as exc:
        raise EmbeddingStoreError("Impossible de lire un embedding local.") from exc

    embedding = embed_text(_memory_embedding_text(memory))
    cluster_key = infer_memory_cluster(memory)
    updated_at = datetime.now(UTC).isoformat()

    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO memory_embeddings
                    (memory_id, model, dimensions, embedding_json, content_hash, cluster_key, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id,
                    settings.eva_embedding_model,
                    len(embedding),
                    json.dumps(embedding, separators=(",", ":")),
                    content_hash,
                    cluster_key,
                    updated_at,
                ),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise EmbeddingStoreError("Impossible d'enregistrer un embedding local.") from exc

    return embedding


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[index] * right[index] for index in range(size))


def search_vector_memories(query: str, limit: int = 8) -> list[VectorMemoryResult]:
    query_embedding = embed_text(query)
    memories = list_memories(limit=settings.eva_memory_vector_candidates)
    results: list[VectorMemoryResult] = []

    for memory in memories:
        try:
            embedding = get_or_create_memory_embedding(memory)
        except EmbeddingStoreError:
            continue
        results.append(
            VectorMemoryResult(
                memory=memory,
                similarity=_cosine_similarity(query_embedding, embedding),
                cluster_key=infer_memory_cluster(memory),
            )
        )

    return sorted(results, key=lambda result: result.similarity, reverse=True)[: max(1, limit)]


def rebuild_memory_embeddings(limit: int = 200) -> dict[str, object]:
    init_embedding_store()
    memories = list_memories(limit=limit)
    indexed = 0
    failed = 0
    errors: list[str] = []

    for memory in memories:
        try:
            get_or_create_memory_embedding(memory)
            indexed += 1
        except EmbeddingStoreError as exc:
            failed += 1
            if len(errors) < 3:
                errors.append(str(exc))

    return {
        "enabled": settings.eva_embeddings_enabled,
        "model": settings.eva_embedding_model,
        "indexed": indexed,
        "failed": failed,
        "errors": errors,
    }


def embedding_status() -> dict[str, object]:
    init_embedding_store()
    try:
        with _connect() as connection:
            _delete_orphan_embeddings(connection)
            connection.commit()
            total_rows = connection.execute("SELECT COUNT(*) AS count FROM memories").fetchone()
            embedded_rows = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM memory_embeddings
                WHERE model = ?
                """,
                (settings.eva_embedding_model,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise EmbeddingStoreError("Impossible de lire le statut vectoriel.") from exc

    return {
        "enabled": settings.eva_embeddings_enabled,
        "model": settings.eva_embedding_model,
        "ollama_base_url": settings.ollama_base_url,
        "memory_count": int(total_rows["count"]) if total_rows else 0,
        "embedding_count": int(embedded_rows["count"]) if embedded_rows else 0,
        "candidate_limit": settings.eva_memory_vector_candidates,
    }
