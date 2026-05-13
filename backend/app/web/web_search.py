from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import unicodedata
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.config import settings


class WebSearchError(Exception):
    """Raised when Eva cannot complete a free web search."""


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[WebSearchResult] = []
        self._in_title = False
        self._in_snippet = False
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []
        self._current_url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        class_name = attrs_dict.get("class", "")

        if tag == "a" and "result__a" in class_name:
            self._in_title = True
            self._current_title = []
            self._current_snippet = []
            self._current_url = _clean_result_url(attrs_dict.get("href", ""))
            return

        if "result__snippet" in class_name:
            self._in_snippet = True
            self._current_snippet = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
            title = _clean_text("".join(self._current_title))
            if title and self._current_url:
                self.results.append(
                    WebSearchResult(
                        title=title,
                        url=self._current_url,
                        snippet="",
                    )
                )
            return

        if self._in_snippet and tag in {"a", "div", "td"}:
            self._in_snippet = False
            snippet = _clean_text("".join(self._current_snippet))
            if snippet and self.results:
                latest = self.results[-1]
                self.results[-1] = WebSearchResult(
                    title=latest.title,
                    url=latest.url,
                    snippet=snippet,
                )

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)


WEB_SEARCH_MARKERS = (
    "cherche sur internet",
    "recherche internet",
    "recherche web",
    "cherche web",
    "trouve sur internet",
    "regarde sur internet",
    "actualite",
    "actualites",
)


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).split())


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _clean_result_url(url: str) -> str:
    clean_url = unescape(url).strip()
    if not clean_url:
        return ""

    parsed = urlparse(clean_url)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])

    return clean_url


def detect_web_search_query(message: str) -> str | None:
    normalized = message.strip()
    lowered = _normalize(normalized)

    for marker in WEB_SEARCH_MARKERS:
        clean_marker = _normalize(marker)
        if clean_marker in lowered:
            query = normalized[lowered.find(clean_marker) + len(clean_marker):].strip(" :,-")
            return query or normalized

    if lowered.startswith(("google ", "web ")):
        return normalized.split(" ", 1)[1].strip()

    return None


async def search_web(query: str, limit: int = 5) -> list[WebSearchResult]:
    if not settings.eva_web_search_enabled:
        raise WebSearchError("La recherche web est desactivee dans la configuration Eva.")

    clean_query = query.strip()
    if not clean_query:
        raise WebSearchError("Recherche web vide.")

    safe_limit = min(max(limit, 1), 8)

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                "https://duckduckgo.com/html/",
                params={"q": clean_query},
                headers={
                    "User-Agent": "EvaLocalAssistant/1.0",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise WebSearchError(
            "La recherche web gratuite n'a pas repondu correctement."
        ) from exc

    parser = _DuckDuckGoParser()
    parser.feed(response.text)

    results = [
        result
        for result in parser.results
        if result.title and result.url
    ][:safe_limit]

    if not results:
        raise WebSearchError("Aucun resultat web exploitable trouve.")

    return results


def format_web_results(query: str, results: list[WebSearchResult]) -> str:
    lines = [f"Recherche web gratuite: {query}", ""]
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. {result.title}")
        lines.append(f"URL: {result.url}")
        if result.snippet:
            lines.append(f"Extrait: {result.snippet}")
        lines.append("")

    return "\n".join(lines).strip()
