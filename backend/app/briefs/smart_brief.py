import asyncio
import html
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

import httpx

from app.briefs.brief_store import Brief, brief_to_dict, save_brief
from app.briefs.rss_brief import RssBriefError, fetch_rss_items, load_sources_config
from app.integrations.inbox_smart import collect_inbox_signals, format_inbox_signals_for_prompt
from app.llm.ollama_client import ask_ollama
from app.memory.profile_store import build_profile_prompt_context


class SmartBriefError(Exception):
    """Raised when Eva cannot prepare the smart brief."""


MAX_ARTICLES_TO_READ = 12
MAX_ARTICLE_CHARS = 9000
MAX_CONTEXT_ARTICLES = 10

KEYWORD_WEIGHTS = {
    "ia": 7,
    "ai": 7,
    "intelligence artificielle": 8,
    "agent": 5,
    "automation": 5,
    "automatisation": 5,
    "openai": 5,
    "anthropic": 5,
    "mistral": 5,
    "startup": 4,
    "business": 4,
    "pme": 4,
    "finance": 4,
    "marche": 3,
    "bourse": 3,
    "regulation": 4,
    "risque": 4,
    "linkedin": 7,
    "prospect": 5,
    "vente": 4,
    "commercial": 4,
    "dreamlense": 10,
    "portrait": 5,
    "photo professionnelle": 8,
    "personal branding": 8,
}

CATEGORY_WEIGHTS = {
    "business": 8,
    "finance": 7,
    "tech": 7,
    "ia": 8,
    "ai": 8,
    "world": 3,
    "general": 1,
}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg).*?>.*?</\1>", " ", value)
    text = re.sub(r"(?is)<(nav|header|footer|aside).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n\n", text)
    text = re.sub(r"(?is)<.*?>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return " ".join(text.split())


def _safe_article_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


async def _fetch_article_text(client: httpx.AsyncClient, url: str) -> str:
    if not _safe_article_url(url):
        return ""

    try:
        response = await client.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 EvaLocalAssistant/1.0"
                )
            },
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return ""

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return ""

    raw = response.text[:1_500_000]
    text = _strip_html(raw)
    blocked_markers = (
        "enable javascript",
        "please enable cookies",
        "access denied",
        "checking your browser",
    )
    if any(marker in text.lower()[:1000] for marker in blocked_markers):
        return ""

    return text[:MAX_ARTICLE_CHARS]


def _pre_score_item(item: dict[str, Any], focus: list[str]) -> int:
    text = _normalize(
        " ".join(
            [
                str(item.get("category", "")),
                str(item.get("title", "")),
                str(item.get("summary", "")),
            ]
        )
    )
    score = CATEGORY_WEIGHTS.get(_normalize(str(item.get("category", "general"))), 0)
    for keyword, weight in KEYWORD_WEIGHTS.items():
        if _normalize(keyword) in text:
            score += weight
    for focus_item in focus:
        if _normalize(str(focus_item)) in text:
            score += 3
    if item.get("image"):
        score += 1
    if item.get("link"):
        score += 1
    return score


def _score_enriched_item(item: dict[str, Any], focus: list[str]) -> dict[str, Any]:
    searchable = _normalize(
        " ".join(
            [
                str(item.get("category", "")),
                str(item.get("title", "")),
                str(item.get("summary", "")),
                str(item.get("article_text", ""))[:4000],
            ]
        )
    )
    score = CATEGORY_WEIGHTS.get(_normalize(str(item.get("category", "general"))), 0)
    tags: list[str] = []

    for keyword, weight in KEYWORD_WEIGHTS.items():
        normalized_keyword = _normalize(keyword)
        if normalized_keyword in searchable:
            score += weight
            if keyword not in tags:
                tags.append(keyword)

    for focus_item in focus:
        normalized_focus = _normalize(str(focus_item))
        if normalized_focus and normalized_focus in searchable:
            score += 3
            if str(focus_item) not in tags:
                tags.append(str(focus_item))

    if item.get("article_text"):
        score += 5
        tags.append("article lu")
    if item.get("image"):
        score += 1
    if item.get("link"):
        score += 1

    item["victor_score"] = min(score, 100)
    item["victor_tags"] = tags[:8]
    item["article_read"] = bool(item.get("article_text"))
    return item


async def _enrich_items(items: list[dict[str, Any]], focus: list[str]) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda item: _pre_score_item(item, focus), reverse=True)
    to_read = ranked[:MAX_ARTICLES_TO_READ]

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        article_texts = await asyncio.gather(
            *[_fetch_article_text(client, str(item.get("link", ""))) for item in to_read]
        )

    for item, article_text in zip(to_read, article_texts, strict=False):
        item["article_text"] = article_text

    enriched_by_link = {str(item.get("link", "")): item for item in to_read}
    enriched_items = []
    for item in items:
        link = str(item.get("link", ""))
        enriched = dict(enriched_by_link.get(link, item))
        enriched_items.append(_score_enriched_item(enriched, focus))

    return sorted(enriched_items, key=lambda item: int(item.get("victor_score", 0)), reverse=True)


def _format_articles_for_prompt(items: list[dict[str, Any]]) -> str:
    blocks = []
    for index, item in enumerate(items[:MAX_CONTEXT_ARTICLES], start=1):
        article = str(item.get("article_text") or item.get("summary") or "")
        blocks.append(
            f"{index}. Score Victor: {item.get('victor_score', 0)}\n"
            f"Tags: {', '.join(item.get('victor_tags', []))}\n"
            f"Source: {item.get('source', 'Source')} / {item.get('category', 'general')}\n"
            f"Titre: {item.get('title', '')}\n"
            f"Lien: {item.get('link', '')}\n"
            f"Image: {item.get('image', '')}\n"
            f"Texte lu/extrait: {article[:2200]}"
        )
    return "\n\n---\n\n".join(blocks)


async def generate_smart_morning_brief() -> Brief:
    payload = await generate_smart_brief_payload()
    return payload["brief"]


async def generate_smart_brief_payload() -> dict[str, Any]:
    config = load_sources_config()
    focus = [str(item) for item in config.get("brief_focus", [])] or [
        "IA",
        "business",
        "finance",
        "DreamLense",
        "opportunites LinkedIn",
        "risques",
    ]

    try:
        rss_items = await fetch_rss_items()
    except RssBriefError as exc:
        raise SmartBriefError(str(exc)) from exc

    if not rss_items:
        raise SmartBriefError(
            "Aucun item RSS n'a pu etre recupere. Verifie data/eva_sources.json ou la connexion internet."
        )

    ranked_items = await _enrich_items([dict(item) for item in rss_items], focus)
    inbox_signals = collect_inbox_signals()

    prompt = f"""
Tu es Eva, l'assistante locale de Victor.
Tu prepares un Smart Brief quotidien vraiment utile, pas une liste d'articles.
Tu as des extraits RSS et, quand possible, le texte complet des articles ouverts.
Tu dois filtrer pour Victor: IA, business, finance, DreamLense, opportunites LinkedIn, risques, tendances utiles pour decider ou creer.

Profil local:
{build_profile_prompt_context()}

Axes prioritaires:
{", ".join(focus)}

Articles classes par score Victor:
{_format_articles_for_prompt(ranked_items)}

Inbox et signaux LinkedIn via Gmail:
{format_inbox_signals_for_prompt(inbox_signals)}

Reponds en francais, avec exactement cette structure:
La premiere ligne de ta reponse doit etre `## 3 choses a savoir ce matin`.
Ne commence pas par "Bien sur", une introduction ou une phrase de politesse.

## 3 choses a savoir ce matin
1. ...
2. ...
3. ...

## 1 opportunite business
...

## 1 risque ou tendance a surveiller
...

## 1 idee LinkedIn
...

## 1 action proposee
...

## Inbox / LinkedIn via Gmail
...

## Sources retenues
- Titre - source - pourquoi c'est pertinent

Regles:
- sois court, direct et actionnable;
- ne cite pas 24 articles;
- indique quand Gmail ou LinkedIn ne sont pas connectes;
- ne pretend jamais avoir publie, envoye ou contacte quelqu'un.
""".strip()

    content = await ask_ollama([{"role": "user", "content": prompt}], mode="dreamlense")
    selected_items = [
        {
            "source": item.get("source", "Source"),
            "category": item.get("category", "general"),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "link": item.get("link", ""),
            "image": item.get("image", ""),
            "victor_score": item.get("victor_score", 0),
            "victor_tags": item.get("victor_tags", []),
            "article_read": item.get("article_read", False),
        }
        for item in ranked_items[:MAX_CONTEXT_ARTICLES]
    ]
    brief = save_brief("Smart Brief Eva", content, selected_items)

    return {
        "brief": brief,
        "brief_dict": brief_to_dict(brief),
        "ranked_items": selected_items,
        "inbox": inbox_signals,
        "stats": {
            "rss_items": len(rss_items),
            "articles_attempted": min(len(rss_items), MAX_ARTICLES_TO_READ),
            "articles_read": sum(1 for item in ranked_items if item.get("article_read")),
            "gmail_available": bool(inbox_signals.get("available")),
            "gmail_messages": len(inbox_signals.get("messages", [])),
            "linkedin_notifications": len(inbox_signals.get("linkedin_notifications", [])),
        },
    }
