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

import httpx

from app.briefs.rss_brief import RssBriefError, fetch_rss_items
from app.config import settings
from app.llm.ollama_client import OllamaClientError, ask_ollama
from app.memory.embedding_store import EmbeddingStoreError, rebuild_memory_embeddings
from app.memory.memory_store import MemoryStoreError, add_memory
from app.memory.obsidian_store import ObsidianMemoryError, ensure_obsidian_vault, mirror_memory_to_obsidian


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


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
CURIOUS_SOURCES_PATH = DATA_DIR / "eva_curiosity_sources.json"
CURIOUS_SOURCES_EXAMPLE_PATH = DATA_DIR / "eva_curiosity_sources.example.json"
CURIOUS_STATE_PATH = DATA_DIR / "eva_curiosity_state.json"
CURIOUS_DB_PATH = DATA_DIR / "eva_curiosity.sqlite"

DEFAULT_FOCUS = (
    "IA",
    "agents autonomes",
    "business",
    "finance",
    "DreamLense",
    "LinkedIn",
    "productivite",
    "machine learning",
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
                    headers={"User-Agent": "EvaLocalAssistant/1.0 curiosity loop"},
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


async def _build_insight(item: CuriosityItem, focus: list[str]) -> str:
    prompt = f"""
Tu es Eva, assistante locale de Victor.
Tu lis une source publique pour t'instruire et enrichir ta memoire.
Ne stocke pas l'article complet. Extrais seulement une lecon courte, utile et reutilisable pour Victor.

Axes Victor: {", ".join(focus)}

Source: {item.source}
Categorie: {item.category}
Titre: {item.title}
URL: {item.url}
Extrait:
{item.excerpt[:2200]}

Reponds en une seule phrase francaise de moins de 420 caracteres.
Structure: "A retenir: ..."
""".strip()
    try:
        insight = await ask_ollama([{"role": "user", "content": prompt}], mode="chat")
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
    rss_items, wiki_items = await asyncio.gather(
        _fetch_rss_curiosity_items(config, focus),
        _fetch_wikipedia_items(config, focus),
    )
    candidates = sorted(
        [*rss_items, *wiki_items],
        key=lambda item: item.score,
        reverse=True,
    )
    min_score = settings.eva_curiosity_min_score
    selected = [
        item
        for item in candidates
        if item.score >= min_score
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
        "last_run_at": datetime.now(UTC).isoformat(),
        "last_result": {
            "candidates": len(candidates),
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
