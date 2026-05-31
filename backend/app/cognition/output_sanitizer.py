import re
import unicodedata

from app.integrations.gmail_client import is_google_reauth_error


RAW_INTERNAL_MARKERS = (
    "resolver eva active",
    "trace locale",
    "ce que j'ai deja tente",
    "ce que jai deja tente",
    "plan de reprise autonome",
    "routes alternatives candidates",
    "etat aucune route",
    "aucune route n'a encore donne",
    "gmail_client failed",
    "web_search failed",
    "browser_assistant failed",
    "beeper_assistant failed",
    "toolresult",
    "invalid_grant",
    "token has been expired or revoked",
)

PRIVATE_WEB_MISROUTE_PATTERNS = (
    r"recherche web gratuite\s*:\s*.*\bmes mails\b",
    r"recherche web gratuite\s*:\s*.*\bgmail\b",
    r"recherche web gratuite\s*:\s*.*\bmes derniers mails\b",
    r"recherche web gratuite\s*:\s*.*\bmes messages\b",
)


def _normalize(text: str) -> str:
    stripped = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    stripped = stripped.replace("’", "'").replace("`", "'")
    return " ".join(stripped.split())


def looks_like_internal_dump(text: str) -> bool:
    normalized = _normalize(text)
    if any(marker in normalized for marker in RAW_INTERNAL_MARKERS):
        return True
    return any(re.search(pattern, normalized) for pattern in PRIVATE_WEB_MISROUTE_PATTERNS)


def sanitize_assistant_output(text: str, *, user_message: str = "", channel: str = "web") -> str:
    if not looks_like_internal_dump(text):
        return text

    normalized = _normalize(f"{user_message}\n{text}")
    if is_google_reauth_error(text) or "gmail" in normalized or "mail" in normalized:
        return "\n".join(
            [
                "Je n'ai pas pu lire tes mails reels pour l'instant.",
                "",
                "La connexion Google locale doit etre reconnectee avant que je puisse lire Gmail/Calendar. Je ne remplace pas tes mails par une recherche web et je n'invente pas de contenu.",
                "",
                "Action: envoie /google depuis Telegram, valide Google sur le PC, puis renvoie ta demande.",
            ]
        )

    if "mes messages" in normalized or "beeper" in normalized or "telegram" in normalized:
        return "\n".join(
            [
                "Je n'ai pas encore une lecture fiable de tes messages.",
                "",
                "Je garde la demande en contexte et je dois reprendre avec l'outil local adapte, pas avec une recherche web generique.",
                "",
                "Prochaine reprise: ouvrir/lire l'app concernee via la vision locale, puis verifier avant de conclure.",
            ]
        )

    suffix = " depuis Telegram" if channel == "telegram" else ""
    return "\n".join(
        [
            "Je n'ai pas encore un resultat fiable.",
            "",
            f"Je garde la demande en contexte{suffix} et je dois changer de route au lieu d'exposer mon diagnostic interne.",
            "Prochaine reprise: utiliser l'outil local le plus proche, verifier une preuve, puis seulement repondre.",
        ]
    )

