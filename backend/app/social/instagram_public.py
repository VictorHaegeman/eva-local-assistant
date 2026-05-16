import json
import re
import shutil
from pathlib import Path
from typing import Any

import httpx


class InstagramPublicError(Exception):
    """Raised when Eva cannot read public Instagram metadata."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
SOCIALS_PATH = DATA_DIR / "eva_socials.json"
SOCIALS_EXAMPLE_PATH = DATA_DIR / "eva_socials.example.json"
SOCIAL_STATE_PATH = DATA_DIR / "eva_social_state.json"


def ensure_socials_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if SOCIALS_PATH.exists():
        return

    if SOCIALS_EXAMPLE_PATH.exists():
        shutil.copyfile(SOCIALS_EXAMPLE_PATH, SOCIALS_PATH)
    else:
        SOCIALS_PATH.write_text(
            json.dumps({"instagram": {"enabled": False, "public_profiles": []}}, indent=2),
            encoding="utf-8",
        )


def load_socials_config() -> dict[str, Any]:
    ensure_socials_file()
    try:
        return json.loads(SOCIALS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstagramPublicError("data/eva_socials.json contient du JSON invalide.") from exc
    except OSError as exc:
        raise InstagramPublicError("Impossible de lire data/eva_socials.json.") from exc


def instagram_status() -> dict[str, object]:
    try:
        config = load_socials_config()
    except InstagramPublicError as exc:
        return {
            "enabled": False,
            "configured_profiles": 0,
            "message": str(exc),
        }

    instagram = config.get("instagram", {})
    if not isinstance(instagram, dict):
        instagram = {}

    profiles = [
        profile
        for profile in instagram.get("public_profiles", [])
        if isinstance(profile, dict) and str(profile.get("url", "")).strip()
    ]

    return {
        "enabled": bool(instagram.get("enabled", False)),
        "configured_profiles": len(profiles),
        "mode": "public_profile_metadata",
        "can_read_private_activity": False,
        "can_read_new_followers": False,
    }


def _extract_meta(html_text: str, property_name: str) -> str:
    pattern = (
        r'<meta[^>]+(?:property|name)=["\']'
        + re.escape(property_name)
        + r'["\'][^>]+content=["\']([^"\']+)["\']'
    )
    match = re.search(pattern, html_text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(SOCIAL_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"instagram": {}}


def _save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOCIAL_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


async def fetch_instagram_public_snapshots() -> dict[str, object]:
    config = load_socials_config()
    instagram = config.get("instagram", {})
    if not isinstance(instagram, dict) or not instagram.get("enabled", False):
        return {
            "enabled": False,
            "profiles": [],
            "summary": "Instagram public non configure.",
        }

    profiles = [
        profile
        for profile in instagram.get("public_profiles", [])
        if isinstance(profile, dict) and str(profile.get("url", "")).strip()
    ]
    if not profiles:
        return {
            "enabled": True,
            "profiles": [],
            "summary": "Aucun profil Instagram public configure.",
        }

    state = _load_state()
    instagram_state = state.setdefault("instagram", {})
    snapshots: list[dict[str, object]] = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
        for profile in profiles:
            url = str(profile.get("url", "")).strip()
            label = str(profile.get("label") or profile.get("username") or url)
            snapshot = {
                "label": label,
                "url": url,
                "accessible": False,
                "title": "",
                "description": "",
                "image": "",
                "changed_since_last_check": False,
                "note": "Lecture publique uniquement.",
            }
            try:
                response = await client.get(url)
                snapshot["status_code"] = response.status_code
                if response.status_code < 400:
                    title = _extract_meta(response.text, "og:title")
                    description = _extract_meta(response.text, "og:description")
                    image = _extract_meta(response.text, "og:image")
                    fingerprint = f"{title}|{description}|{image}"
                    previous = instagram_state.get(url, {}).get("fingerprint")
                    snapshot.update(
                        {
                            "accessible": True,
                            "title": title,
                            "description": description,
                            "image": image,
                            "changed_since_last_check": bool(previous and previous != fingerprint),
                        }
                    )
                    instagram_state[url] = {
                        "fingerprint": fingerprint,
                        "title": title,
                        "description": description,
                        "image": image,
                    }
            except httpx.HTTPError as exc:
                snapshot["note"] = f"Profil non lisible publiquement: {exc}"

            snapshots.append(snapshot)

    _save_state(state)

    changed = [snapshot for snapshot in snapshots if snapshot.get("changed_since_last_check")]
    if changed:
        summary = f"{len(changed)} profil Instagram public a change depuis le dernier check."
    else:
        summary = "Aucun changement public Instagram detecte."

    return {
        "enabled": True,
        "profiles": snapshots,
        "summary": summary,
        "limits": (
            "Les nouveaux abonnes et statistiques privees ne sont pas accessibles "
            "sans integration officielle ou session autorisee."
        ),
    }
