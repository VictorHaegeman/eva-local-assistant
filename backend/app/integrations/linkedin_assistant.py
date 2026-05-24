import html
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from app.actions.action_store import ActionStoreError, create_action
from app.config import settings
from app.integrations.linkedin_browser import DEFAULT_LINKEDIN_COMPOSE_URL
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
        "company_page_url": profile.get("company_page_url", ""),
        "browser_compose_url": _linkedin_compose_url(profile),
        "browser_bridge": settings.eva_linkedin_enabled,
        "can_prepare_browser_post": settings.eva_linkedin_enabled,
        "official_api_connected": False,
        "can_publish": False,
        "mode": "draft_plus_browser_prepare",
        "note": (
            "Eva prepare des posts, commentaires et idees LinkedIn. "
            "Elle peut ouvrir LinkedIn dans le navigateur et copier un brouillon, "
            "mais elle ne clique pas sur Publier."
        ),
    }


def _format_linkedin_context() -> str:
    profile = load_linkedin_profile()
    return json.dumps(profile, ensure_ascii=False, indent=2)


def _linkedin_compose_url(profile: dict[str, Any] | None = None) -> str:
    profile = profile or load_linkedin_profile()
    return str(
        profile.get("company_admin_url")
        or profile.get("browser_compose_url")
        or profile.get("company_page_url")
        or DEFAULT_LINKEDIN_COMPOSE_URL
    ).strip()


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.lower().startswith("json"):
            clean = clean[4:].strip()

    start = clean.find("{")
    end = clean.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LinkedInAssistantError("Ollama n'a pas renvoye de JSON exploitable.")

    try:
        payload = json.loads(clean[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LinkedInAssistantError("JSON LinkedIn invalide renvoye par Ollama.") from exc

    return payload if isinstance(payload, dict) else {}


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


async def draft_linkedin_browser_package(topic: str) -> dict[str, Any]:
    if not settings.eva_linkedin_enabled:
        raise LinkedInAssistantError("LinkedIn assistant est desactive.")

    prompt = f"""
Tu prepares un post LinkedIn pour Victor/DreamLense.
Tu ne publies rien. Tu ne dis jamais que le post a ete publie.
Le post doit etre pret a coller dans LinkedIn, premium, clair, utile et credible.
Si une image est utile, propose un prompt image, mais ne pretend pas l'avoir creee.

Profil Eva:
{build_profile_prompt_context()}

Contexte LinkedIn local:
{_format_linkedin_context()}

Demande de Victor:
{topic}

Reponds uniquement en JSON valide, sans markdown:
{{
  "post_text": "texte final du post pret a coller",
  "image_recommendation": "none | generate_visual | use_existing",
  "image_prompt": "prompt image si utile, sinon chaine vide",
  "checks": ["point a verifier avant publication"]
}}
""".strip()

    try:
        raw = await ask_ollama([{"role": "user", "content": prompt}], mode="dreamlense")
    except OllamaClientError as exc:
        raise LinkedInAssistantError(str(exc)) from exc

    try:
        payload = _extract_json_object(raw)
    except LinkedInAssistantError:
        fallback = await draft_linkedin_post(topic, format_name="post pret a publier")
        payload = {
            "post_text": fallback,
            "image_recommendation": "none",
            "image_prompt": "",
            "checks": ["Relire le texte avant publication."],
        }

    post_text = str(payload.get("post_text", "")).strip()
    if not post_text:
        raise LinkedInAssistantError("Ollama n'a pas genere de texte LinkedIn.")

    checks = payload.get("checks", [])
    if not isinstance(checks, list):
        checks = [str(checks)]

    return {
        "post_text": post_text,
        "image_recommendation": str(payload.get("image_recommendation", "none")).strip() or "none",
        "image_prompt": str(payload.get("image_prompt", "")).strip(),
        "checks": [str(check).strip() for check in checks if str(check).strip()],
    }


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
    if wants_linkedin_activity(message):
        return False
    return "linkedin" in normalized and any(
        marker in normalized
        for marker in ("post", "idee", "idees", "contenu", "commentaire", "reponse", "redige")
    )


def wants_linkedin_activity(message: str) -> bool:
    normalized = _normalize(message)
    if "linkedin" not in normalized:
        return False

    activity_markers = (
        "activite",
        "activites",
        "notification",
        "notifications",
        "message",
        "messages",
        "compte",
        "abonnes",
        "abonne",
        "followers",
        "connexion",
        "connexions",
        "invitation",
        "invitations",
        "commentaires",
        "likes",
        "statistiques",
        "stats",
        "nouveaux",
        "nouvelles",
    )
    creation_markers = (
        "post",
        "publie",
        "publier",
        "poster",
        "poste",
        "redige",
        "ecris",
        "contenu",
        "idee de post",
        "commentaire linkedin",
    )
    return any(marker in normalized for marker in activity_markers) and not any(
        marker in normalized for marker in creation_markers
    )


def wants_linkedin_browser_post(message: str) -> bool:
    normalized = _normalize(message)
    if "linkedin" not in normalized:
        return False
    if wants_linkedin_activity(message):
        return False

    browser_markers = (
        "publie",
        "publier",
        "poste",
        "poster",
        "post ",
        "faire un post",
        "fais un post",
        "cree un post",
        "creer un post",
        "ouvre",
        "navigateur",
        "dreamlense",
    )
    passive_markers = ("idee", "idees", "brouillon", "commentaire", "reponse")

    if any(marker in normalized for marker in ("publie", "publier", "poster", "poste", "ouvre", "navigateur")):
        return True

    if any(marker in normalized for marker in browser_markers) and not any(
        marker in normalized for marker in passive_markers
    ):
        return True

    return False


def _format_linkedin_signal(message: dict[str, Any], index: int) -> str:
    subject = _clean_linkedin_text(str(message.get("subject") or "(sans objet)"))
    sender = _clean_linkedin_text(str(message.get("from") or ""))
    date = _clean_linkedin_text(str(message.get("date") or ""))
    snippet = _clean_linkedin_text(str(message.get("snippet") or message.get("body") or ""))[:500]
    lines = [f"{index}. {subject}"]
    if sender:
        lines.append(f"   De: {sender}")
    if date:
        lines.append(f"   Date: {date}")
    if snippet:
        lines.append(f"   Signal: {snippet}")
    return "\n".join(lines)


def _clean_linkedin_text(value: str) -> str:
    clean = html.unescape(value)
    clean = re.sub(r"[\u034f\u061c\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


async def build_linkedin_activity_response(message: str) -> str | None:
    if not wants_linkedin_activity(message):
        return None

    from app.integrations.inbox_smart import collect_inbox_signals

    signals = collect_inbox_signals(max_inbox=2, max_linkedin=8, include_bodies=False)
    if not signals.get("available"):
        return (
            "Source: Gmail/LinkedIn notifications locales.\n"
            f"{signals.get('summary', 'Gmail indisponible.')}\n\n"
            "Je n'ai pas invente d'activite LinkedIn. Pour lire tes signaux LinkedIn sans API LinkedIn, "
            "Eva utilise d'abord les notifications LinkedIn recues dans Gmail."
        )

    notifications = signals.get("linkedin_notifications", [])
    if not notifications:
        return (
            "Source: Gmail API, notifications LinkedIn reelles.\n"
            "Aucun signal LinkedIn recent trouve dans les notifications Gmail lues.\n\n"
            "Je n'ai pas prepare de post et je n'ai rien publie. "
            "Pour une lecture plus directe du compte LinkedIn, il faudra un mode navigateur/vision dedie."
        )

    lines = [
        "Source: Gmail API, notifications LinkedIn reelles.",
        f"{len(notifications)} signal(s) LinkedIn recent(s) detecte(s).",
        "",
        "Activite LinkedIn disponible:",
    ]
    lines.extend(
        _format_linkedin_signal(notification, index)
        for index, notification in enumerate(notifications[:8], start=1)
    )
    lines.extend(
        [
            "",
            "Lecture rapide:",
            "Je n'ai pas prepare de post LinkedIn pour cette demande. "
            "J'ai uniquement lu les signaux disponibles et je peux ensuite ouvrir LinkedIn si tu veux consulter un element precis.",
        ]
    )
    return "\n".join(lines)


async def prepare_linkedin_browser_post(message: str) -> str:
    profile = load_linkedin_profile()
    package = await draft_linkedin_browser_package(message)
    try:
        action = create_action(
            action_type="linkedin_browser_prepare_post",
            title="Preparer un post LinkedIn dans le navigateur",
            description=(
                "Copie le texte dans le presse-papiers et ouvre LinkedIn. "
                "Le clic final Publier reste manuel."
            ),
            payload={
                "post_text": package["post_text"],
                "target_url": _linkedin_compose_url(profile),
                "image_prompt": package["image_prompt"],
                "image_recommendation": package["image_recommendation"],
                "checks": package["checks"],
            },
        )
    except ActionStoreError as exc:
        raise LinkedInAssistantError(str(exc)) from exc

    from app.actions.executor import execute_action

    try:
        result = execute_action(action.id, require_approval=False)
    except Exception as exc:
        raise LinkedInAssistantError(str(exc)) from exc
    executed_action = result.get("action", {})
    if not result.get("executed"):
        raise LinkedInAssistantError(str(executed_action.get("result") or "Impossible d'ouvrir LinkedIn."))

    lines = [
        "J'ai prepare le post LinkedIn, ouvert LinkedIn et lance le remplissage automatique du compositeur.",
        "Si LinkedIn etait deja connecte et que la fenetre etait prete, le brouillon est colle dans la zone de post.",
        "Rien n'a ete publie automatiquement: Eva s'arrete avant le clic public final.",
        "Le texte reste aussi dans le presse-papiers comme secours si LinkedIn n'a pas pris le focus.",
        "",
        "Post prepare:",
        package["post_text"],
    ]

    if package["image_recommendation"] != "none":
        lines.extend(
            [
                "",
                f"Image recommandee: {package['image_recommendation']}",
                package["image_prompt"] or "Choisis une image DreamLense pertinente avant publication.",
            ]
        )

    if package["checks"]:
        lines.append("")
        lines.append("A verifier avant publication:")
        lines.extend(f"- {check}" for check in package["checks"])

    return "\n".join(lines)


async def build_linkedin_chat_response(message: str) -> str | None:
    activity = await build_linkedin_activity_response(message)
    if activity:
        return activity

    if wants_linkedin_browser_post(message):
        return await prepare_linkedin_browser_post(message)

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
