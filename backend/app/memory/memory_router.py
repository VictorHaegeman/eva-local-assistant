from dataclasses import dataclass, field

from app.agents.intent_router import UserIntent, classify_user_intent
from app.memory.cluster_store import (
    ClusterRoute,
    cluster_label,
    get_memory_cluster,
    infer_memory_cluster,
    route_memory_clusters,
)
from app.memory.embedding_store import (
    EmbeddingStoreError,
    EmbeddingUnavailableError,
    VectorMemoryResult,
    search_vector_memories,
)
from app.memory.memory_store import Memory, MemorySearchResult, search_memories


@dataclass
class RoutedMemoryResult:
    memory: Memory
    score: float
    cluster_key: str
    signals: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutedMemoryContext:
    query: str
    intent_name: str
    intent_summary: str
    clusters: list[ClusterRoute]
    results: list[RoutedMemoryResult]
    vector_available: bool
    vector_error: str = ""


INTENT_CLUSTER_HINTS: dict[str, tuple[str, ...]] = {
    "google_oauth_setup": ("gmail_calendar", "eva_operating_rules"),
    "calendar_read": ("gmail_calendar", "victor_identity"),
    "gmail_read": ("gmail_calendar", "dreamlense", "housing", "writing_preferences"),
    "gmail_reply_audit": ("gmail_calendar", "dreamlense", "writing_preferences"),
    "gmail_reply_draft": ("gmail_calendar", "writing_preferences", "dreamlense", "housing"),
    "project_factory": ("code_projects", "dreamlense", "eva_operating_rules"),
    "cursor_work": ("code_projects", "eva_operating_rules"),
    "terminal_error": ("code_projects", "eva_operating_rules"),
    "screen_read": ("eva_operating_rules", "messages"),
    "local_status": ("eva_operating_rules",),
}


def _cluster_keys(routes: list[ClusterRoute]) -> set[str]:
    return {route.cluster.key for route in routes}


def _route_clusters_with_intent(query: str, intent: UserIntent, limit: int = 4) -> list[ClusterRoute]:
    combined: dict[str, ClusterRoute] = {
        route.cluster.key: route for route in route_memory_clusters(query, limit=limit)
    }

    for index, cluster_key in enumerate(INTENT_CLUSTER_HINTS.get(intent.name, ())):
        cluster = get_memory_cluster(cluster_key)
        if not cluster:
            continue
        score = max(0.42, intent.confidence - (index * 0.08))
        existing = combined.get(cluster_key)
        if existing and existing.score >= score:
            continue
        combined[cluster_key] = ClusterRoute(cluster=cluster, score=min(score, 1.0))

    return sorted(combined.values(), key=lambda route: route.score, reverse=True)[: max(1, limit)]


def _expanded_query(query: str, intent: UserIntent, clusters: list[ClusterRoute]) -> str:
    parts = [
        query,
        f"Intent: {intent.name}",
        f"Objectif interprete: {intent.summary}",
    ]
    for route in clusters:
        parts.append(
            f"Cluster: {route.cluster.label}. {route.cluster.description}. "
            f"Mots cles: {', '.join(route.cluster.keywords)}"
        )
    return "\n".join(parts)


def _add_lexical_scores(
    combined: dict[int, RoutedMemoryResult],
    lexical_results: list[MemorySearchResult],
    routed_cluster_keys: set[str],
) -> None:
    for rank, result in enumerate(lexical_results):
        memory = result.memory
        cluster_key = infer_memory_cluster(memory)
        score = 0.48 / (rank + 1)
        if memory.category in {"identity", "preference", "project", "operating_rule"}:
            score += 0.06
        if cluster_key in routed_cluster_keys:
            score += 0.08

        existing = combined.get(memory.id)
        if existing:
            existing.score += score
            existing.signals["lexical"] = max(existing.signals.get("lexical", 0.0), score)
            continue

        combined[memory.id] = RoutedMemoryResult(
            memory=memory,
            score=score,
            cluster_key=cluster_key,
            signals={"lexical": score},
        )


def _add_vector_scores(
    combined: dict[int, RoutedMemoryResult],
    vector_results: list[VectorMemoryResult],
    routed_cluster_keys: set[str],
) -> None:
    for result in vector_results:
        memory = result.memory
        normalized_similarity = max(0.0, min((result.similarity + 1.0) / 2.0, 1.0))
        score = normalized_similarity * 0.62
        if result.cluster_key in routed_cluster_keys:
            score += 0.10

        existing = combined.get(memory.id)
        if existing:
            existing.score += score
            existing.cluster_key = result.cluster_key
            existing.signals["vector"] = max(existing.signals.get("vector", 0.0), normalized_similarity)
            existing.signals["cluster_boost"] = 1.0 if result.cluster_key in routed_cluster_keys else 0.0
            continue

        combined[memory.id] = RoutedMemoryResult(
            memory=memory,
            score=score,
            cluster_key=result.cluster_key,
            signals={
                "vector": normalized_similarity,
                "cluster_boost": 1.0 if result.cluster_key in routed_cluster_keys else 0.0,
            },
        )


def route_memory(query: str, limit: int = 8) -> RoutedMemoryContext:
    intent = classify_user_intent(query)
    clusters = _route_clusters_with_intent(query, intent)
    retrieval_query = _expanded_query(query, intent, clusters)
    routed_cluster_keys = _cluster_keys(clusters)
    combined: dict[int, RoutedMemoryResult] = {}

    lexical_results = search_memories(retrieval_query, limit=max(limit * 2, 8))
    _add_lexical_scores(combined, lexical_results, routed_cluster_keys)

    vector_available = True
    vector_error = ""
    try:
        vector_results = search_vector_memories(retrieval_query, limit=max(limit * 2, 8))
        _add_vector_scores(combined, vector_results, routed_cluster_keys)
    except EmbeddingUnavailableError as exc:
        vector_available = False
        vector_error = str(exc)
    except EmbeddingStoreError as exc:
        vector_available = False
        vector_error = str(exc)

    ranked = sorted(combined.values(), key=lambda result: result.score, reverse=True)[: max(1, limit)]
    return RoutedMemoryContext(
        query=query,
        intent_name=intent.name,
        intent_summary=intent.summary,
        clusters=clusters,
        results=ranked,
        vector_available=vector_available,
        vector_error=vector_error,
    )


def build_relevant_memory_prompt_context(query: str) -> str:
    context = route_memory(query, limit=8)
    if not context.results:
        fallback = (
            "Memoire hybride: aucune memoire locale specifique trouvee. "
            "N'invente pas de souvenirs."
        )
        if not context.vector_available and context.vector_error:
            fallback += f"\nMemoire vectorielle indisponible: {context.vector_error}"
        return fallback

    cluster_line = (
        ", ".join(f"{route.cluster.label} ({round(route.score * 100)}%)" for route in context.clusters)
        if context.clusters
        else "aucun cluster dominant"
    )
    lines = [
        "Memoires pertinentes retrouvees par routeur hybride local.",
        f"Intent memoire: {context.intent_name} - {context.intent_summary}",
        f"Clusters probables: {cluster_line}.",
        (
            "Recherche utilisee: FTS5/BM25 + embeddings Ollama locaux."
            if context.vector_available
            else "Recherche utilisee: FTS5/BM25. Embeddings indisponibles."
        ),
        "Utilise-les seulement si elles aident la demande actuelle.",
    ]
    if not context.vector_available and context.vector_error:
        lines.append(f"Note technique: {context.vector_error}")

    for result in context.results:
        memory = result.memory
        label = cluster_label(result.cluster_key)
        lines.append(
            f"- [{label} | {memory.category}/{memory.source} | score {result.score:.2f}] "
            f"{memory.content}"
        )
    return "\n".join(lines)
