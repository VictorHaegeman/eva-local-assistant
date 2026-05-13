import html
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from app.briefs.brief_store import Brief, save_brief
from app.llm.ollama_client import ask_ollama


class RssBriefError(Exception):
    """Raised when Eva cannot build a morning brief."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
SOURCES_PATH = DATA_DIR / "eva_sources.json"
SOURCES_EXAMPLE_PATH = DATA_DIR / "eva_sources.example.json"

MAX_ITEMS_PER_SOURCE = 6
MAX_TOTAL_ITEMS = 24


def ensure_sources_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if SOURCES_PATH.exists():
        return

    if SOURCES_EXAMPLE_PATH.exists():
        shutil.copyfile(SOURCES_EXAMPLE_PATH, SOURCES_PATH)
    else:
        SOURCES_PATH.write_text(
            json.dumps({"sources": [], "brief_focus": []}, indent=2),
            encoding="utf-8",
        )


def load_sources_config() -> dict[str, Any]:
    ensure_sources_file()

    try:
        payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RssBriefError("data/eva_sources.json contient du JSON invalide.") from exc
    except OSError as exc:
        raise RssBriefError("Impossible de lire data/eva_sources.json.") from exc

    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        raise RssBriefError("sources doit etre une liste dans data/eva_sources.json.")

    return payload


def _strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(without_tags).split())


def _find_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in list(element):
        clean_tag = child.tag.split("}")[-1].lower()
        if clean_tag in names and child.text:
            return _strip_html(child.text)
    return ""


def _parse_feed(xml_text: str, source: dict[str, Any]) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []

    rss_items = root.findall(".//item")
    atom_items = [
        element
        for element in root.iter()
        if element.tag.split("}")[-1].lower() == "entry"
    ]

    for item in [*rss_items, *atom_items][:MAX_ITEMS_PER_SOURCE]:
        title = _find_text(item, ("title",))
        summary = _find_text(item, ("description", "summary", "content"))
        link = _find_text(item, ("link",))

        if not link:
            for child in list(item):
                if child.tag.split("}")[-1].lower() == "link":
                    link = child.attrib.get("href", "")
                    break

        if not title:
            continue

        items.append(
            {
                "source": str(source.get("name", "Source")),
                "category": str(source.get("category", "general")),
                "title": title,
                "summary": summary[:500],
                "link": link,
            }
        )

    return items


async def fetch_rss_items() -> list[dict[str, str]]:
    config = load_sources_config()
    sources = [source for source in config.get("sources", []) if isinstance(source, dict)]
    collected_items: list[dict[str, str]] = []

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for source in sources:
            url = str(source.get("url", "")).strip()
            if not url.startswith(("http://", "https://")):
                continue

            try:
                response = await client.get(url)
                response.raise_for_status()
                collected_items.extend(_parse_feed(response.text, source))
            except (httpx.HTTPError, ET.ParseError):
                continue

            if len(collected_items) >= MAX_TOTAL_ITEMS:
                break

    return collected_items[:MAX_TOTAL_ITEMS]


async def generate_morning_brief() -> Brief:
    config = load_sources_config()
    focus = config.get("brief_focus", ["business", "tech", "IA", "finance", "DreamLense"])
    items = await fetch_rss_items()

    if not items:
        raise RssBriefError(
            "Aucun item RSS n'a pu etre recupere. Verifie data/eva_sources.json ou la connexion internet."
        )

    source_lines = []
    for index, item in enumerate(items, start=1):
        source_lines.append(
            f"{index}. [{item['category']}] {item['title']} - {item['source']}\n"
            f"Resume source: {item.get('summary', '')}\n"
            f"Lien: {item.get('link', '')}"
        )

    prompt = f"""
Tu prepares le brief du matin de Victor.

Objectif:
- resumer les informations utiles;
- separer business, tech, IA, finance et DreamLense quand possible;
- signaler les opportunites ou risques;
- proposer 3 idees LinkedIn ou business concretes;
- rester concis et actionnable.

Axes prioritaires: {", ".join(str(item) for item in focus)}

Sources RSS recuperees:
{chr(10).join(source_lines)}
""".strip()

    content = await ask_ollama([{"role": "user", "content": prompt}])
    return save_brief("Brief du matin", content, items)
