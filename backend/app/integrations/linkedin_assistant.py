import json
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from app.config import settings
from app.llm.ollama_client import OllamaClientError, ask_ollama
from app.memory.profile_store import build_profile_prompt_context


class LinkedInAssistantError(Exception):
    """Raised when Eva cannot prepare LinkedIn work."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
LINKEDIN_PATH = DATA_DIR / "eva_linkedin.json"
LINKEDIN_EXAMPLE_PATH = DATA_DIR / "eva_linkedin.example.json"


def ensure_linkedin_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if LINKEDIN_PATH.exists():
        return
    if LINKEDIN_EXAMPLE_PATH.exists():
        shutil.copyfile(LINKEDIN_EXAMPLE_PATH, LINKEDIN_PATH)
    else:
        LINKEDIN_PATH.write_text(json.dumps({}, indent=2), encoding="utf-8")


def load_linkedin_profile() -> dict[str, Any]:
    ensure_linkedin_file()
    try:
        payload = json.loads(LINKEDIN_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LinkedInAssistantError("data/eva_linkedin.json contient du JSON invalide.") from exc
    return payload if isinstance(payload, dict) else {}


def linkedin_status() -> dict[str, Any]:
    profile = load_linkedin_profile()
    return {
        "enabled": settings.eva_linkedin_enabled,
        "configured": bool(profile),
        "profile_url": profile.get("profile_url", ""),
        "official_api_connected": False,
        "can_publish": False,
        "mode": "draft_only",
        "note": (
            "Eva prepare des posts, commentaires et idees LinkedIn. "
            "Elle ne publie pas et ne scrape pas LinkedIn."
        ),
    }


def _format_linkedin_context() -> str:
    profile = load_linkedin_profile()
    return json.dumps(profile, ensure_ascii=False, indent=2)


async def draft_linkedin_post(
    topic: str,
    angle: str = "",
    audience: str = "",
    format_name: str = "post court",
) -> str:
    if not settings.eva_linkedin_enabled:
        raise LinkedInAssistantError("LinkedIn assistant est desactive.")

    prompt = f"""
Tu prepares un brouillon LinkedIn pour Victor.
Ne publie rien. Ne dis jamais que le post a ete publie.
Le style doit etre premium, clair, utile et humain.

Profil Eva:
{build_profile_prompt_context()}

Contexte LinkedIn local:
{_format_linkedin_context()}

Sujet:
{topic}

Angle:
{angle or "angle business utile et concret"}

Audience:
{audience or "audience par defaut du profil LinkedIn local"}

Format:
{format_name}

Donne:
1. accroche;
2. post final;
3. variantes de hook;
4. CTA;
5. points a verifier avant publication.
""".strip()

    try:
        return await ask_ollama([{"role": "user", "content": prompt}], mode="dreamlense")
    except OllamaClientError as exc:
        raise LinkedInAssistantError(str(exc)) from exc


async def draft_linkedin_comment(post_context: str, intent: str = "") -> str:
    if not settings.eva_linkedin_enabled:
        raise LinkedInAssistantError("LinkedIn assistant est desactive.")

    prompt = f"""
Tu prepares un brouillon de commentaire LinkedIn pour Victor.
Ne publie rien.
Le commentaire doit etre naturel, utile, court et professionnel.

Contexte LinkedIn local:
{_format_linkedin_context()}

Post ou contexte:
{post_context}

Intention:
{intent or "apporter une reponse utile et credible"}

Donne 3 options de commentaire.
""".strip()

    try:
        return await ask_ollama([{"role": "user", "content": prompt}], mode="dreamlense")
    except OllamaClientError as exc:
        raise LinkedInAssistantError(str(exc)) from exc


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def wants_linkedin_draft(message: str) -> bool:
    normalized = _normalize(message)
    return "linkedin" in normalized and any(
        marker in normalized
        for marker in ("post", "idee", "idees", "contenu", "commentaire", "reponse", "redige")
    )


async def build_linkedin_chat_response(message: str) -> str | None:
    if not wants_linkedin_draft(message):
        return None

    if any(marker in _normalize(message) for marker in ("commentaire", "reponse")):
        draft = await draft_linkedin_comment(message)
    else:
        draft = await draft_linkedin_post(message)

    return (
        "J'ai prepare un brouillon LinkedIn. Rien n'a ete publie.\n\n"
        f"{draft}"
    )
