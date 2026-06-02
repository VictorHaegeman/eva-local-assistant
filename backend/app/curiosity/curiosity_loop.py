import asyncio
import json
import re
import shutil
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.briefs.rss_brief import RssBriefError, fetch_rss_items
from app.config import settings
from app.llm.ollama_client import OllamaClientError, ask_ollama_json
from app.memory.embedding_store import EmbeddingStoreError, rebuild_memory_embeddings
from app.memory.memory_store import MemoryStoreError, add_memory
from app.memory.obsidian_store import ObsidianMemoryError, ensure_obsidian_vault, mirror_memory_to_obsidian
from app.web.web_search import WebSearchError, search_web


class CuriosityError(Exception):
    """Raised when Eva cannot run the local curiosity loop."""


@dataclass(frozen=True)
class CuriosityItem:
    source: str
    category: str
    title: str
    url: str
    excerpt: str
    score: int
    tags: tuple[str, ...]


@dataclass(frozen=True)
class CuriosityTopic:
    title: str
    language: str
    category: str
    priority: int
    reason: str


@dataclass(frozen=True)
class SocialPublicQuery:
    query: str
    category: str
    priority: int
    reason: str


@dataclass(frozen=True)
class SocialPublicProfile:
    handle: str
    url: str
    category: str
    priority: int
    reason: str


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
CURIOUS_SOURCES_PATH = DATA_DIR / "eva_curiosity_sources.json"
CURIOUS_SOURCES_EXAMPLE_PATH = DATA_DIR / "eva_curiosity_sources.example.json"
CURIOUS_STATE_PATH = DATA_DIR / "eva_curiosity_state.json"
CURIOUS_DB_PATH = DATA_DIR / "eva_curiosity.sqlite"
WIKIMEDIA_USER_AGENT = (
    "EvaLocalAssistant/1.0 "
    "(https://github.com/VictorHaegeman/eva-local-assistant; local personal assistant)"
)

DEFAULT_FOCUS = (
    "IA",
    "agents autonomes",
    "business",
    "finance",
    "DreamLense",
    "LinkedIn",
    "Twitter",
    "X",
    "social behavior",
    "creator economy",
    "productivite",
    "machine learning",
)

DEFAULT_WIKIPEDIA_TOPICS: tuple[CuriosityTopic, ...] = (
    CuriosityTopic(
        title="Artificial intelligence",
        language="en",
        category="ai",
        priority=30,
        reason="socle general IA",
    ),
    CuriosityTopic(
        title="Large language model",
        language="en",
        category="ai",
        priority=32,
        reason="cerveau local et agents",
    ),
    CuriosityTopic(
        title="Autonomous agent",
        language="en",
        category="agents",
        priority=34,
        reason="autonomie Eva",
    ),
    CuriosityTopic(
        title="Retrieval-augmented generation",
        language="en",
        category="memory",
        priority=36,
        reason="memoire vectorielle Eva",
    ),
    CuriosityTopic(
        title="Machine learning",
        language="en",
        category="machine_learning",
        priority=30,
        reason="apprentissage local",
    ),
    CuriosityTopic(
        title="Reinforcement learning",
        language="en",
        category="machine_learning",
        priority=34,
        reason="bonus/malus Eva",
    ),
    CuriosityTopic(
        title="Cluster analysis",
        language="en",
        category="machine_learning",
        priority=28,
        reason="clusters memoire",
    ),
    CuriosityTopic(
        title="Productivity",
        language="en",
        category="productivity",
        priority=22,
        reason="assistant personnel",
    ),
)

DEFAULT_SOCIAL_PUBLIC_QUERIES: tuple[SocialPublicQuery, ...] = (
    SocialPublicQuery(
        query='site:x.com ("AI agents" OR "autonomous agents") ("build" OR "workflow" OR "automation")',
        category="social_ai_agents",
        priority=30,
        reason="comprendre comment les builders parlent des agents IA",
    ),
    SocialPublicQuery(
        query='site:x.com ("local AI" OR Ollama OR "open source AI") ("agent" OR "assistant")',
        category="social_local_ai",
        priority=28,
        reason="reperer les patterns autour de l'IA locale gratuite",
    ),
    SocialPublicQuery(
        query='site:x.com (LinkedIn OR "personal brand") ("AI" OR "startup") ("hook" OR "post" OR "growth")',
        category="social_content",
        priority=24,
        reason="ameliorer les angles de posts et la comprehension des reactions sociales",
    ),
    SocialPublicQuery(
        query='site:x.com ("AI headshots" OR "professional portraits" OR "personal branding")',
        category="social_dreamlense",
        priority=34,
        reason="surveiller des signaux utiles pour DreamLense",
    ),
)

DEFAULT_SOCIAL_PUBLIC_PROFILES: tuple[SocialPublicProfile, ...] = (
    SocialPublicProfile(
        handle="OpenAI",
        url="https://x.com/OpenAI",
        category="social_ai_profile",
        priority=18,
        reason="observer le positionnement public d'un acteur IA majeur",
    ),
    SocialPublicProfile(
        handle="GoogleDeepMind",
        url="https://x.com/GoogleDeepMind",
        category="social_ai_profile",
        priority=18,
        reason="observer comment un laboratoire IA presente ses avancees",
    ),
    SocialPublicProfile(
        handle="ycombinator",
        url="https://x.com/ycombinator",
        category="social_startup_profile",
        priority=18,
        reason="observer le langage startup et opportunites business",
    ),
    SocialPublicProfile(
        handle="levelsio",
        url="https://x.com/levelsio",
        category="social_builder_profile",
        priority=20,
        reason="observer les signaux indie builder, produit et distribution",
    ),
)

KEYWORD_WEIGHTS = {
    "ia": 7,
    "ai": 7,
    "intelligence artificielle": 8,
    "agent": 6,
    "autonomous": 5,
    "automation": 5,
    "automatisation": 5,
    "machine learning": 6,
    "llm": 5,
    "ollama": 7,
    "local": 3,
    "startup": 4,
    "business": 4,
    "linkedin": 6,
    "twitter": 5,
    "x.com": 5,
    "social": 4,
    "post": 4,
    "hook": 5,
    "viral": 4,
    "creator": 4,
    "audience": 4,
    "community": 4,
    "growth": 5,
    "vente": 5,
    "prospect": 5,
    "portrait": 6,
    "photo professionnelle": 8,
    "dreamlense": 12,
    "finance": 5,
    "risque": 4,
    "regulation": 4,
    "productivite": 4,
}


def ensure_curiosity_sources_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CURIOUS_SOURCES_PATH.exists():
        return
    if CURIOUS_SOURCES_EXAMPLE_PATH.exists():
        shutil.copyfile(CURIOUS_SOURCES_EXAMPLE_PATH, CURIOUS_SOURCES_PATH)
    else:
        CURIOUS_SOURCES_PATH.write_text(
            json.dumps({"focus": list(DEFAULT_FOCUS)}, indent=2),
            encoding="utf-8",
        )


def load_curiosity_config() -> dict[str, Any]:
    ensure_curiosity_sources_file()
    try:
        payload = json.loads(CURIOUS_SOURCES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CuriosityError("data/eva_curiosity_sources.json contient du JSON invalide.") from exc
    except OSError as exc:
        raise CuriosityError("Impossible de lire data/eva_curiosity_sources.json.") from exc
    return payload if isinstance(payload, dict) else {"focus": list(DEFAULT_FOCUS)}


def init_curiosity_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_curiosity_sources_file()
    try:
        with sqlite3.connect(CURIOUS_DB_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS curiosity_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    insight TEXT NOT NULL,
                    memory_id INTEGER,
                    UNIQUE(url)
                )
                """
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise CuriosityError("Impossible d'initialiser la curiosite locale Eva.") from exc


def _connect() -> sqlite3.Connection:
    init_curiosity_store()
    connection = sqlite3.connect(CURIOUS_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _load_state() -> dict[str, Any]:
    if not CURIOUS_STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(CURIOUS_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CURIOUS_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _contains_term(haystack: str, term: str) -> bool:
    normalized_term = _normalize(term).strip()
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in haystack
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _strip_text(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", str(value or "")).split())


def _focus_terms(config: dict[str, Any]) -> list[str]:
    raw_focus = config.get("focus", [])
    if not isinstance(raw_focus, list):
        return list(DEFAULT_FOCUS)
    focus = [str(item).strip() for item in raw_focus if str(item).strip()]
    return focus or list(DEFAULT_FOCUS)


def _int_from_config(payload: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(payload.get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def _topic_from_config(payload: Any) -> CuriosityTopic | None:
    if isinstance(payload, str):
        title = payload.strip()
        return CuriosityTopic(title=title, language="en", category="wikipedia", priority=18, reason="topic manuel") if title else None
    if not isinstance(payload, dict):
        return None

    title = str(payload.get("title", "")).strip()
    if not title:
        return None
    language = str(payload.get("language", "en")).strip() or "en"
    category = str(payload.get("category", "wikipedia")).strip() or "wikipedia"
    reason = str(payload.get("reason", "topic configure")).strip() or "topic configure"
    priority = _int_from_config(payload, "priority", 22, 0, 100)
    return CuriosityTopic(
        title=title,
        language=language,
        category=category,
        priority=priority,
        reason=reason,
    )


def _configured_wikipedia_topics(config: dict[str, Any]) -> list[CuriosityTopic]:
    wikipedia = config.get("wikipedia", {})
    if not isinstance(wikipedia, dict):
        return list(DEFAULT_WIKIPEDIA_TOPICS)
    raw_topics = wikipedia.get("topics", [])
    if not isinstance(raw_topics, list):
        return list(DEFAULT_WIKIPEDIA_TOPICS)
    topics = [topic for topic in (_topic_from_config(item) for item in raw_topics) if topic]
    return topics or list(DEFAULT_WIKIPEDIA_TOPICS)


def _social_query_from_config(payload: Any) -> SocialPublicQuery | None:
    if isinstance(payload, str):
        query = payload.strip()
        return SocialPublicQuery(
            query=query,
            category="social_public",
            priority=18,
            reason="requete sociale configuree",
        ) if query else None
    if not isinstance(payload, dict):
        return None

    query = str(payload.get("query", "")).strip()
    if not query:
        return None
    category = str(payload.get("category", "social_public")).strip() or "social_public"
    reason = str(payload.get("reason", "veille sociale publique")).strip() or "veille sociale publique"
    priority = _int_from_config(payload, "priority", 24, 0, 100)
    return SocialPublicQuery(
        query=query,
        category=category,
        priority=priority,
        reason=reason,
    )


def _configured_social_queries(config: dict[str, Any]) -> list[SocialPublicQuery]:
    social_public = config.get("social_public", {})
    if not isinstance(social_public, dict):
        return list(DEFAULT_SOCIAL_PUBLIC_QUERIES)
    raw_queries = social_public.get("queries", [])
    if not isinstance(raw_queries, list):
        return list(DEFAULT_SOCIAL_PUBLIC_QUERIES)
    queries = [query for query in (_social_query_from_config(item) for item in raw_queries) if query]
    return queries or list(DEFAULT_SOCIAL_PUBLIC_QUERIES)


def _social_profile_from_config(payload: Any) -> SocialPublicProfile | None:
    if isinstance(payload, str):
        handle = payload.strip().lstrip("@")
        if not handle:
            return None
        return SocialPublicProfile(
            handle=handle,
            url=f"https://x.com/{handle}",
            category="social_public_profile",
            priority=18,
            reason="profil social public configure",
        )
    if not isinstance(payload, dict):
        return None

    handle = str(payload.get("handle", "")).strip().lstrip("@")
    url = str(payload.get("url", "")).strip()
    if not url and handle:
        url = f"https://x.com/{handle}"
    if not handle and url:
        handle = url.rstrip("/").rsplit("/", 1)[-1].lstrip("@")
    if not handle or not url.startswith(("https://x.com/", "https://twitter.com/")):
        return None
    category = str(payload.get("category", "social_public_profile")).strip() or "social_public_profile"
    reason = str(payload.get("reason", "profil social public configure")).strip() or "profil social public configure"
    priority = _int_from_config(payload, "priority", 18, 0, 100)
    return SocialPublicProfile(
        handle=handle,
        url=url,
        category=category,
        priority=priority,
        reason=reason,
    )


def _configured_social_profiles(config: dict[str, Any]) -> list[SocialPublicProfile]:
    social_public = config.get("social_public", {})
    if not isinstance(social_public, dict):
        return list(DEFAULT_SOCIAL_PUBLIC_PROFILES)
    raw_profiles = social_public.get("profiles", [])
    if not isinstance(raw_profiles, list):
        return list(DEFAULT_SOCIAL_PUBLIC_PROFILES)
    profiles = [profile for profile in (_social_profile_from_config(item) for item in raw_profiles) if profile]
    return profiles or list(DEFAULT_SOCIAL_PUBLIC_PROFILES)


def _score_item(title: str, excerpt: str, category: str, focus: list[str]) -> tuple[int, tuple[str, ...]]:
    haystack = _normalize(f"{category} {title} {excerpt}")
    score = 0
    tags: list[str] = []
    for keyword, weight in KEYWORD_WEIGHTS.items():
        if _contains_term(haystack, keyword):
            score += weight
            tags.append(keyword)
    for term in focus:
        if _contains_term(haystack, term):
            score += 3
            tags.append(term)
    return min(score, 100), tuple(dict.fromkeys(tags[:8]))


def _passes_quality_gate(item: CuriosityItem, min_score: int) -> bool:
    if item.score < min_score:
        return False
    if len(item.excerpt.strip()) < 120:
        return False
    if _already_seen(item.url, item.title):
        return False
    return True


def _already_seen(url: str, title: str) -> bool:
    try:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM curiosity_items
                WHERE url = ? OR lower(title) = lower(?)
                LIMIT 1
                """,
                (url, title),
            ).fetchone()
    except sqlite3.Error:
        return False
    return bool(row)


async def _fetch_wikipedia_items(config: dict[str, Any], focus: list[str]) -> list[CuriosityItem]:
    wikipedia = config.get("wikipedia", {})
    if not isinstance(wikipedia, dict) or not bool(wikipedia.get("enabled", True)):
        return []

    languages = wikipedia.get("languages", ["fr", "en"])
    if not isinstance(languages, list):
        languages = ["fr", "en"]

    try:
        pages_per_run = int(wikipedia.get("pages_per_run") or settings.eva_curiosity_wikipedia_pages)
    except (TypeError, ValueError):
        pages_per_run = settings.eva_curiosity_wikipedia_pages
    pages_per_run = min(max(pages_per_run, 0), 6)

    urls: list[str] = []
    for language in [str(item).strip() for item in languages if str(item).strip()][:3]:
        for _ in range(pages_per_run):
            urls.append(f"https://{language}.wikipedia.org/api/rest_v1/page/random/summary")

    items: list[CuriosityItem] = []
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for url in urls:
            try:
                response = await client.get(
                    url,
                    headers={"User-Agent": WIKIMEDIA_USER_AGENT},
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                continue

            title = _strip_text(str(payload.get("title", "")))
            excerpt = _strip_text(str(payload.get("extract", "")))[:1200]
            page_url = str(payload.get("content_urls", {}).get("desktop", {}).get("page", "")).strip()
            if not title or not page_url or _already_seen(page_url, title):
                continue
            score, tags = _score_item(title, excerpt, "wikipedia", focus)
            items.append(
                CuriosityItem(
                    source="Wikipedia",
                    category="wikipedia",
                    title=title,
                    url=page_url,
                    excerpt=excerpt,
                    score=score,
                    tags=tags,
                )
            )
    return items


async def _fetch_wikipedia_targeted_items(
    config: dict[str, Any],
    focus: list[str],
    state: dict[str, Any],
) -> tuple[list[CuriosityItem], int]:
    wikipedia = config.get("wikipedia", {})
    if not isinstance(wikipedia, dict) or not bool(wikipedia.get("enabled", True)):
        return [], int(state.get("wikipedia_topic_offset") or 0)

    topics = _configured_wikipedia_topics(config)
    pages_per_run = _int_from_config(wikipedia, "targeted_pages_per_run", 4, 0, 12)
    if not topics or pages_per_run <= 0:
        return [], int(state.get("wikipedia_topic_offset") or 0)

    current_offset = int(state.get("wikipedia_topic_offset") or 0)
    selected_topics = [topics[(current_offset + index) % len(topics)] for index in range(min(pages_per_run, len(topics)))]
    next_offset = (current_offset + len(selected_topics)) % len(topics)

    items: list[CuriosityItem] = []
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for topic in selected_topics:
            title_slug = quote(topic.title.replace(" ", "_"), safe="")
            url = f"https://{topic.language}.wikipedia.org/api/rest_v1/page/summary/{title_slug}"
            try:
                response = await client.get(
                    url,
                    headers={"User-Agent": WIKIMEDIA_USER_AGENT},
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                continue

            title = _strip_text(str(payload.get("title", topic.title)))
            excerpt = _strip_text(str(payload.get("extract", "")))[:1400]
            page_url = str(payload.get("content_urls", {}).get("desktop", {}).get("page", "")).strip()
            if not title or not page_url or _already_seen(page_url, title):
                continue

            base_score, tags = _score_item(title, excerpt, topic.category, focus)
            tags = tuple(list(dict.fromkeys((*tags, topic.category, "self-study")))[:10])
            items.append(
                CuriosityItem(
                    source="Wikipedia self-study",
                    category=topic.category,
                    title=title,
                    url=page_url,
                    excerpt=f"{excerpt}\n\nPourquoi Eva lit ce sujet: {topic.reason}",
                    score=min(base_score + topic.priority, 100),
                    tags=tags,
                )
            )
    return items, next_offset


async def _fetch_rss_curiosity_items(config: dict[str, Any], focus: list[str]) -> list[CuriosityItem]:
    rss = config.get("rss", {})
    if isinstance(rss, dict) and not bool(rss.get("reuse_eva_sources", True)):
        return []

    try:
        rss_items = await fetch_rss_items()
    except RssBriefError:
        return []

    items: list[CuriosityItem] = []
    for item in rss_items:
        title = _strip_text(str(item.get("title", "")))
        excerpt = _strip_text(str(item.get("summary", "")))[:1200]
        url = str(item.get("link", "")).strip()
        if not title or not url or _already_seen(url, title):
            continue
        category = str(item.get("category", "rss"))
        score, tags = _score_item(title, excerpt, category, focus)
        items.append(
            CuriosityItem(
                source=str(item.get("source", "RSS")),
                category=category,
                title=title,
                url=url,
                excerpt=excerpt,
                score=score,
                tags=tags,
            )
        )
    return items


async def _fetch_social_public_items(config: dict[str, Any], focus: list[str]) -> list[CuriosityItem]:
    social_public = config.get("social_public", {})
    if not isinstance(social_public, dict) or not bool(social_public.get("enabled", False)):
        return []

    queries = _configured_social_queries(config)
    max_queries = _int_from_config(social_public, "max_queries_per_run", 3, 0, 8)
    results_per_query = _int_from_config(social_public, "results_per_query", 3, 1, 6)
    profiles = _configured_social_profiles(config)
    max_profiles = _int_from_config(social_public, "max_profiles_per_run", 3, 0, 8)

    items: list[CuriosityItem] = []
    for configured_query in queries[:max_queries]:
        try:
            results = await search_web(configured_query.query, limit=results_per_query)
        except WebSearchError:
            continue

        for result in results:
            url = str(result.url or "").strip()
            title = _strip_text(result.title)
            snippet = _strip_text(result.snippet)[:700]
            if not url or not title or _already_seen(url, title):
                continue
            if "x.com" not in _normalize(url) and "twitter.com" not in _normalize(url):
                continue

            excerpt = _strip_text(
                " ".join(
                    [
                        snippet,
                        f"Signal social public detecte via recherche X/Twitter: {configured_query.query}.",
                        f"Pourquoi Eva lit ce signal: {configured_query.reason}.",
                        "Objectif: comprendre les comportements, hooks, objections, angles et idees qui circulent publiquement.",
                    ]
                )
            )[:1400]
            base_score, tags = _score_item(title, excerpt, configured_query.category, focus)
            tags = tuple(
                list(
                    dict.fromkeys(
                        (
                            *tags,
                            configured_query.category,
                            "twitter",
                            "x_public",
                            "social_signal",
                        )
                    )
                )[:10]
            )
            items.append(
                CuriosityItem(
                    source="X/Twitter public search",
                    category=configured_query.category,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    score=min(base_score + configured_query.priority, 100),
                    tags=tags,
                )
            )

    if max_profiles > 0:
        async with httpx.AsyncClient(timeout=16.0, follow_redirects=True) as client:
            for profile in profiles[:max_profiles]:
                day_key = datetime.now(UTC).date().isoformat()
                stored_url = f"{profile.url}#eva-profile-{day_key}"
                if _already_seen(stored_url, f"X/Twitter public profile @{profile.handle} {day_key}"):
                    continue
                try:
                    response = await client.get(
                        profile.url,
                        headers={"User-Agent": "Mozilla/5.0 EvaLocalAssistant/1.0"},
                    )
                    response.raise_for_status()
                except httpx.HTTPError:
                    continue

                profile_text = _extract_x_public_profile_text(response.text)
                if not profile_text:
                    continue
                excerpt = _strip_text(
                    " ".join(
                        [
                            f"Profil public X/Twitter observe: @{profile.handle}.",
                            profile_text,
                            f"Pourquoi Eva lit ce profil: {profile.reason}.",
                            "Objectif: comprendre les signaux publics, positioning, hooks, audience et comportements.",
                        ]
                    )
                )[:1400]
                base_score, tags = _score_item(
                    f"X/Twitter public profile @{profile.handle}",
                    excerpt,
                    profile.category,
                    focus,
                )
                tags = tuple(
                    list(
                        dict.fromkeys(
                            (
                                *tags,
                                profile.category,
                                "twitter",
                                "x_public",
                                "social_profile",
                            )
                        )
                    )[:10]
                )
                items.append(
                    CuriosityItem(
                        source="X/Twitter public profile",
                        category=profile.category,
                        title=f"X/Twitter public profile @{profile.handle}",
                        url=stored_url,
                        excerpt=excerpt,
                        score=min(base_score + profile.priority, 100),
                        tags=tags,
                    )
                )

    return items


def _extract_json_string_values(text: str, key: str, limit: int = 12) -> list[str]:
    pattern = rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"'
    values: list[str] = []
    for raw_value in re.findall(pattern, text)[:limit]:
        try:
            decoded = json.loads(f'"{raw_value}"')
        except json.JSONDecodeError:
            decoded = raw_value
        clean_value = _strip_text(str(decoded))
        if clean_value and clean_value not in values:
            values.append(clean_value)
    return values


def _extract_x_public_profile_text(html_text: str) -> str:
    descriptions = [
        value
        for value in _extract_json_string_values(html_text, "description", limit=18)
        if 18 <= len(value) <= 320 and "opensearchdescription" not in _normalize(value)
    ]
    names = _extract_json_string_values(html_text, "name", limit=8)
    screen_names = _extract_json_string_values(html_text, "screen_name", limit=8)
    followers_match = re.search(r'"followers_count"\s*:\s*(\d+)', html_text)
    followers = followers_match.group(1) if followers_match else ""

    chunks: list[str] = []
    if names:
        chunks.append(f"Nom public: {names[0]}.")
    if screen_names:
        chunks.append(f"Handle detecte: @{screen_names[0]}.")
    if descriptions:
        chunks.append(f"Bio publique: {descriptions[0]}.")
    if followers:
        chunks.append(f"Followers publics detectes: {followers}.")

    return " ".join(chunks)


async def _build_insight(item: CuriosityItem, focus: list[str]) -> str:
    social_instruction = ""
    if item.source.startswith("X/Twitter"):
        social_instruction = """
Pour un signal X/Twitter public, ne resume pas seulement le contenu.
Extrais surtout une lecon sociale utile: pourquoi ca attire l'attention, quel comportement humain on observe, quel angle de post ou de produit Victor peut reutiliser, et quelle limite verifier.
""".strip()

    system_prompt = f"""
Tu es Eva, assistante locale de Victor.
Tu transformes une source publique en micro-apprentissage local.
Ne stocke jamais l'article complet.
Retourne uniquement du JSON valide: {{"insight":"A retenir: ..."}}
La valeur insight doit faire moins de 420 caracteres, en francais, utile et reutilisable.
{social_instruction}
""".strip()

    user_prompt = f"""
Axes Victor: {", ".join(focus)}

Source: {item.source}
Categorie: {item.category}
Titre: {item.title}
URL: {item.url}
Extrait:
{item.excerpt[:2200]}
""".strip()
    try:
        payload = await ask_ollama_json(
            system_prompt,
            user_prompt,
            timeout_seconds=min(settings.ollama_reasoning_timeout_seconds, 18.0),
            temperature=0.2,
        )
        insight = str(payload.get("insight", "")).strip()
        if not insight:
            raise OllamaClientError("Insight vide.")
        if not _normalize(insight).startswith("a retenir"):
            insight = f"A retenir: {insight}"
    except OllamaClientError:
        insight = f"A retenir: {item.title} semble pertinent pour {', '.join(item.tags[:3]) or 'la veille de Victor'}."
    return " ".join(insight.split())[:520]


def _store_curiosity_result(item: CuriosityItem, insight: str, memory_id: int | None) -> None:
    created_at = datetime.now(UTC).isoformat()
    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO curiosity_items (
                    created_at, source, category, title, url, score, tags_json, insight, memory_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    item.source,
                    item.category,
                    item.title,
                    item.url,
                    item.score,
                    json.dumps(list(item.tags), ensure_ascii=True),
                    insight,
                    memory_id,
                ),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise CuriosityError("Impossible de stocker une lecture curiosity.") from exc


def _append_obsidian_report(items: list[dict[str, Any]]) -> str:
    if not settings.eva_obsidian_memory_enabled or not items:
        return ""
    try:
        vault = ensure_obsidian_vault()
        target_dir = vault / "85 - Curiosity"
        target_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().date().isoformat()
        path = target_dir / f"Curiosity {today}.md"
        if not path.exists():
            path.write_text(
                f"# Curiosity {today}\n\n[[INDEX]]\n\nLectures autonomes publiques d'Eva.\n\n",
                encoding="utf-8",
            )
        blocks = []
        for item in items:
            blocks.append(
                "\n".join(
                    [
                        f"## {item['title']}",
                        f"- Source: {item['source']}",
                        f"- Score: {item['score']}",
                        f"- Tags: {', '.join(item.get('tags', []))}",
                        f"- URL: {item['url']}",
                        f"- Memoire: #{item.get('memory_id') or 'non stockee'}",
                        f"- Insight: {item['insight']}",
                        "",
                    ]
                )
            )
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(blocks))
        return str(path)
    except (OSError, ObsidianMemoryError):
        return ""


async def run_curiosity_once(force: bool = False) -> dict[str, Any]:
    init_curiosity_store()
    if not settings.eva_curiosity_enabled and not force:
        return {
            "enabled": False,
            "ran": False,
            "reason": "Curiosity desactivee. Active EVA_CURIOSITY_ENABLED=true ou lance avec force=true.",
        }

    config = load_curiosity_config()
    focus = _focus_terms(config)
    state = _load_state()
    rss_items, wiki_items, targeted_result, social_items = await asyncio.gather(
        _fetch_rss_curiosity_items(config, focus),
        _fetch_wikipedia_items(config, focus),
        _fetch_wikipedia_targeted_items(config, focus, state),
        _fetch_social_public_items(config, focus),
    )
    targeted_items, next_wikipedia_offset = targeted_result
    candidates = sorted(
        [*social_items, *targeted_items, *rss_items, *wiki_items],
        key=lambda item: item.score,
        reverse=True,
    )
    min_score = settings.eva_curiosity_min_score
    selected = [
        item
        for item in candidates
        if _passes_quality_gate(item, min_score)
    ][: max(1, settings.eva_curiosity_max_items_per_run)]

    learned: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in selected:
        insight = await _build_insight(item, focus)
        memory_content = (
            f"Veille autonome: {insight} Source: {item.source} - {item.title}. URL: {item.url}"
        )[:590]
        memory_id = None
        try:
            memory = add_memory(
                memory_content,
                category="curiosity",
                source="curiosity_loop",
                confidence=0.66,
            )
            memory_id = memory.id
            try:
                mirror_memory_to_obsidian(memory)
            except ObsidianMemoryError:
                pass
        except MemoryStoreError as exc:
            errors.append(str(exc))

        _store_curiosity_result(item, insight, memory_id)
        learned.append(
            {
                "title": item.title,
                "source": item.source,
                "category": item.category,
                "url": item.url,
                "score": item.score,
                "tags": list(item.tags),
                "insight": insight,
                "memory_id": memory_id,
            }
        )

    report_path = _append_obsidian_report(learned)
    embeddings = None
    if learned and settings.eva_curiosity_rebuild_embeddings:
        try:
            embeddings = rebuild_memory_embeddings(limit=400)
        except EmbeddingStoreError as exc:
            errors.append(str(exc))

    state = {
        **state,
        "wikipedia_topic_offset": next_wikipedia_offset,
        "last_run_at": datetime.now(UTC).isoformat(),
        "last_result": {
            "candidates": len(candidates),
            "targeted_candidates": len(targeted_items),
            "social_candidates": len(social_items),
            "rss_candidates": len(rss_items),
            "random_wikipedia_candidates": len(wiki_items),
            "learned": len(learned),
            "report_path": report_path,
            "errors": errors,
        },
    }
    _save_state(state)

    return {
        "enabled": settings.eva_curiosity_enabled,
        "ran": True,
        "candidates": len(candidates),
        "targeted_candidates": len(targeted_items),
        "social_candidates": len(social_items),
        "rss_candidates": len(rss_items),
        "random_wikipedia_candidates": len(wiki_items),
        "learned": learned,
        "errors": errors,
        "report_path": report_path,
        "embeddings": embeddings,
    }


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    try:
        tags = json.loads(str(row["tags_json"]))
    except json.JSONDecodeError:
        tags = []
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "source": str(row["source"]),
        "category": str(row["category"]),
        "title": str(row["title"]),
        "url": str(row["url"]),
        "score": int(row["score"]),
        "tags": tags if isinstance(tags, list) else [],
        "insight": str(row["insight"]),
        "memory_id": row["memory_id"],
    }


def list_curiosity_items(limit: int = 30) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit), 1), 200)
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM curiosity_items
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise CuriosityError("Impossible de lire les lectures curiosity.") from exc
    return [_row_to_dict(row) for row in rows]


def curiosity_status(limit: int = 20) -> dict[str, Any]:
    init_curiosity_store()
    config = load_curiosity_config()
    state = _load_state()
    try:
        with _connect() as connection:
            total = connection.execute("SELECT COUNT(*) AS count FROM curiosity_items").fetchone()
    except sqlite3.Error as exc:
        raise CuriosityError("Impossible de lire le statut curiosity.") from exc
    return {
        "enabled": settings.eva_curiosity_enabled,
        "interval_minutes": settings.eva_curiosity_interval_minutes,
        "max_items_per_run": settings.eva_curiosity_max_items_per_run,
        "min_score": settings.eva_curiosity_min_score,
        "sources_path": str(CURIOUS_SOURCES_PATH),
        "db_path": str(CURIOUS_DB_PATH),
        "focus": _focus_terms(config),
        "rules": config.get("rules", []),
        "wikipedia_topics": [
            {
                "title": topic.title,
                "language": topic.language,
                "category": topic.category,
                "priority": topic.priority,
                "reason": topic.reason,
            }
            for topic in _configured_wikipedia_topics(config)
        ],
        "social_public": {
            "enabled": bool(config.get("social_public", {}).get("enabled", False))
            if isinstance(config.get("social_public", {}), dict)
            else False,
            "queries": [
                {
                    "query": query.query,
                    "category": query.category,
                    "priority": query.priority,
                    "reason": query.reason,
                }
                for query in _configured_social_queries(config)
            ],
            "profiles": [
                {
                    "handle": profile.handle,
                    "url": profile.url,
                    "category": profile.category,
                    "priority": profile.priority,
                    "reason": profile.reason,
                }
                for profile in _configured_social_profiles(config)
            ],
        },
        "total_items": int(total["count"]) if total else 0,
        "state": state,
        "recent": list_curiosity_items(limit=limit),
    }


async def curiosity_loop() -> None:
    while True:
        if settings.eva_curiosity_enabled:
            try:
                await run_curiosity_once(force=False)
            except Exception:
                pass
        await asyncio.sleep(max(settings.eva_curiosity_interval_minutes * 60, 900))


def start_curiosity_background_task() -> asyncio.Task[None] | None:
    if not settings.eva_curiosity_enabled:
        return None
    return asyncio.create_task(curiosity_loop())
