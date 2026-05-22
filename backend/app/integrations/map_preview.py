import re
import unicodedata
from urllib.parse import quote_plus, urlencode

import httpx


class MapPreviewError(Exception):
    """Raised when Eva cannot prepare an embedded map preview."""


MAP_MARKERS = (
    "carte",
    "map",
    "plan",
    "localise",
    "localiser",
    "situe",
    "situer",
)

MAP_STOPWORDS = (
    "ouvre",
    "ouvrir",
    "affiche",
    "montre",
    "montre moi",
    "montre-moi",
    "pull up",
    "dans le chat",
    "sur la carte",
    "une carte",
    "la carte",
    "un plan",
    "le plan",
    "map of",
    "carte de",
    "carte d",
    "plan de",
    "plan d",
    "stp",
    "s il te plait",
)

KNOWN_PLACES = {
    "londres": {
        "label": "Londres, Royaume-Uni",
        "lat": 51.5074,
        "lon": -0.1278,
        "bbox": (-0.5103, 51.2868, 0.3340, 51.6919),
    },
    "london": {
        "label": "London, United Kingdom",
        "lat": 51.5074,
        "lon": -0.1278,
        "bbox": (-0.5103, 51.2868, 0.3340, 51.6919),
    },
    "paris": {
        "label": "Paris, France",
        "lat": 48.8566,
        "lon": 2.3522,
        "bbox": (2.2241, 48.8156, 2.4699, 48.9022),
    },
    "bruxelles": {
        "label": "Bruxelles, Belgique",
        "lat": 50.8503,
        "lon": 4.3517,
        "bbox": (4.2450, 50.7630, 4.4820, 50.9130),
    },
    "brussels": {
        "label": "Brussels, Belgium",
        "lat": 50.8503,
        "lon": 4.3517,
        "bbox": (4.2450, 50.7630, 4.4820, 50.9130),
    },
    "new york": {
        "label": "New York, Etats-Unis",
        "lat": 40.7128,
        "lon": -74.0060,
        "bbox": (-74.2591, 40.4774, -73.7004, 40.9176),
    },
    "tokyo": {
        "label": "Tokyo, Japon",
        "lat": 35.6762,
        "lon": 139.6503,
        "bbox": (139.5620, 35.5280, 139.9100, 35.8170),
    },
}


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def detect_map_query(message: str) -> str | None:
    normalized = _normalize(message)
    if not any(marker in normalized for marker in MAP_MARKERS):
        return None

    query = normalized
    for marker in sorted(MAP_STOPWORDS, key=len, reverse=True):
        query = re.sub(rf"\b{re.escape(marker)}\b", " ", query).strip()

    query = re.sub(r"\b(?:de|du|des|d|a|sur|pour|of|the|a|an)\b", " ", query)
    query = re.sub(r"[,;:!?]", " ", query)
    query = " ".join(query.split())

    if len(query) < 2:
        return None
    return query


def _map_urls(label: str, lat: float, lon: float, bbox: tuple[float, float, float, float]) -> dict[str, str]:
    west, south, east, north = bbox
    bbox_value = f"{west},{south},{east},{north}"
    embed_query = urlencode(
        {
            "bbox": bbox_value,
            "layer": "mapnik",
            "marker": f"{lat},{lon}",
        }
    )
    return {
        "url": f"https://www.openstreetmap.org/search?query={quote_plus(label)}",
        "embed_url": f"https://www.openstreetmap.org/export/embed.html?{embed_query}",
    }


async def _geocode_place(query: str) -> dict[str, object] | None:
    normalized = _normalize(query)
    if normalized in KNOWN_PLACES:
        place = KNOWN_PLACES[normalized]
        urls = _map_urls(str(place["label"]), float(place["lat"]), float(place["lon"]), place["bbox"])
        return {
            **place,
            **urls,
            "source": "known_place",
        }

    headers = {
        "User-Agent": "EvaLocalAssistant/1.0 local map preview",
        "Accept": "application/json",
    }
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            response = await client.get("https://nominatim.openstreetmap.org/search", params=params)
            response.raise_for_status()
    except httpx.HTTPError:
        return None

    payload = response.json()
    if not isinstance(payload, list) or not payload:
        return None

    first = payload[0]
    try:
        lat = float(first["lat"])
        lon = float(first["lon"])
        south, north, west, east = [float(value) for value in first["boundingbox"]]
    except (KeyError, TypeError, ValueError):
        delta = 0.05
        south = lat - delta
        north = lat + delta
        west = lon - delta
        east = lon + delta

    label = str(first.get("display_name") or query)
    urls = _map_urls(label, lat, lon, (west, south, east, north))
    return {
        "label": label,
        "lat": lat,
        "lon": lon,
        "bbox": (west, south, east, north),
        **urls,
        "source": "openstreetmap_nominatim",
    }


async def build_map_preview_from_message(message: str) -> dict[str, object] | None:
    query = detect_map_query(message)
    if not query:
        return None

    place = await _geocode_place(query)
    if not place:
        return {
            "content": (
                f"Je n'ai pas trouve de carte fiable pour: {query}. "
                "Je peux ouvrir une recherche web si tu veux."
            ),
            "web_preview": None,
        }

    label = str(place["label"])
    return {
        "content": (
            f"Carte interactive: {label}.\n"
            "Je l'affiche directement dans le chat avec OpenStreetMap."
        ),
        "web_preview": {
            "type": "map",
            "provider": "OpenStreetMap",
            "title": f"Carte - {label}",
            "label": label,
            "url": place["url"],
            "embed_url": place["embed_url"],
            "lat": place["lat"],
            "lon": place["lon"],
            "source": place["source"],
        },
    }
