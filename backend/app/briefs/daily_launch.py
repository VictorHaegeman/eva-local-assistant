import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.briefs.brief_store import Brief, brief_to_dict, get_latest_brief
from app.briefs.rss_brief import RssBriefError
from app.briefs.smart_brief import SmartBriefError, generate_smart_morning_brief
from app.config import settings
from app.social.instagram_public import InstagramPublicError, fetch_instagram_public_snapshots


class DailyLaunchError(Exception):
    """Raised when Eva cannot prepare the daily launch brief."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DAILY_STATE_PATH = DATA_DIR / "eva_daily_launch.json"


def _today_key() -> str:
    return datetime.now().date().isoformat()


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(DAILY_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _item_score(item: dict[str, Any]) -> int:
    category = str(item.get("category", "")).lower()
    score = 0
    if category in {"world", "business", "finance", "tech"}:
        score += 3
    if item.get("image"):
        score += 2
    if item.get("link"):
        score += 1
    return score


def _select_visual_items(brief: Brief, limit: int = 6) -> list[dict[str, object]]:
    sorted_items = sorted(brief.items, key=_item_score, reverse=True)
    visual_items: list[dict[str, object]] = []
    for item in sorted_items[:limit]:
        visual_items.append(
            {
                "source": item.get("source", "Source"),
                "category": item.get("category", "general"),
                "title": item.get("title", ""),
                "summary": item.get("summary", ""),
                "link": item.get("link", ""),
                "image": item.get("image", ""),
            }
        )
    return visual_items


def _select_tabs(brief: Brief) -> list[dict[str, object]]:
    max_tabs = max(0, min(settings.eva_daily_brief_max_tabs, 8))
    tabs: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in sorted(brief.items, key=_item_score, reverse=True):
        link = str(item.get("link", "")).strip()
        if not link or link in seen:
            continue
        seen.add(link)
        tabs.append(
            {
                "title": item.get("title", "Source"),
                "url": link,
                "source": item.get("source", "Source"),
                "category": item.get("category", "general"),
            }
        )
        if len(tabs) >= max_tabs:
            break
    return tabs


async def get_daily_launch_brief(force: bool = False) -> dict[str, object]:
    today = _today_key()
    state = _load_state()

    if not settings.eva_daily_brief_enabled:
        return {
            "enabled": False,
            "should_show": False,
            "reason": "daily brief desactive",
        }

    if not force and state.get("last_success_date") == today:
        return {
            "enabled": True,
            "should_show": False,
            "reason": "deja affiche aujourd'hui",
            "last_success_date": state.get("last_success_date"),
        }

    try:
        brief = await generate_smart_morning_brief()
        stale = False
    except (RssBriefError, SmartBriefError) as exc:
        latest = get_latest_brief()
        if not latest:
            raise DailyLaunchError(str(exc)) from exc
        brief = latest
        stale = True

    try:
        instagram = await fetch_instagram_public_snapshots()
    except InstagramPublicError as exc:
        instagram = {
            "enabled": False,
            "summary": str(exc),
            "profiles": [],
        }

    state.update(
        {
            "last_success_date": today,
            "last_brief_id": brief.id,
            "updated_at": datetime.now().isoformat(),
        }
    )
    _save_state(state)

    return {
        "enabled": True,
        "should_show": True,
        "date": today,
        "stale": stale,
        "brief": brief_to_dict(brief),
        "visual_items": _select_visual_items(brief),
        "suggested_tabs": _select_tabs(brief),
        "auto_open_tabs": settings.eva_daily_brief_auto_open_tabs,
        "instagram": instagram,
    }
