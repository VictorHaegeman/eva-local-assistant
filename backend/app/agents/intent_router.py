import unicodedata
from dataclasses import dataclass
from typing import Literal


IntentName = Literal[
    "terminal_error",
    "screen_read",
    "google_oauth_setup",
    "calendar_read",
    "gmail_read",
    "gmail_reply_draft",
    "project_factory",
    "cursor_work",
    "local_status",
    "generic_chat",
]


@dataclass(frozen=True)
class UserIntent:
    name: IntentName
    confidence: float
    summary: str
    caution: str = ""


def normalize_intent_text(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def classify_user_intent(message: str) -> UserIntent:
    text = normalize_intent_text(message)

    if _has_any(
        text,
        (
            "commandnotfoundexception",
            "n'est pas reconnu",
            "not recognized as",
            "fullyqualifiederrorid",
            "categoryinfo",
            "traceback",
            "err_connection_refused",
        ),
    ):
        return UserIntent(
            name="terminal_error",
            confidence=0.95,
            summary="Diagnostiquer une erreur terminal et appliquer un correctif connu si possible.",
        )

    if _has_any(
        text,
        (
            "lis l'ecran",
            "lis mon ecran",
            "regarde l'ecran",
            "regarde mon ecran",
            "analyse l'ecran",
            "analyse mon ecran",
            "screen",
            "pixels",
            "capture d'ecran",
            "ce qu'il y a a l'ecran",
            "ce qu il y a a l ecran",
        ),
    ):
        return UserIntent(
            name="screen_read",
            confidence=0.9,
            summary="Lire les pixels de l'ecran local et interpreter ce qui est visible.",
            caution="La capture reste locale et peut contenir des donnees privees.",
        )

    google_context = _has_any(
        text,
        ("google", "gmail", "oauth", "calendar", "calendrier", "compte google"),
    )
    google_setup_action = _has_any(
        text,
        (
            "connect",
            "connexion",
            "autorisation",
            "authentification",
            "oauth",
            "credentials",
            "credential",
            "script",
            "token",
            "recupere",
            "recuperer",
            "trouve moi",
            "va recuperer",
            "colle",
            "coller",
            "la ou il faut",
        ),
    )
    if google_context and google_setup_action:
        caution = ""
        if _has_any(text, ("colle", "coller", "dans le code")):
            caution = (
                "Le JSON OAuth ne doit pas etre colle dans le code. "
                "Il doit rester dans data/gmail_credentials.json, ignore par Git."
            )
        return UserIntent(
            name="google_oauth_setup",
            confidence=0.94,
            summary=(
                "Configurer l'acces Google local: retrouver/creer le JSON OAuth, "
                "lancer le flux de consentement, puis stocker le token localement."
            ),
            caution=caution,
        )

    if _has_any(text, ("agenda", "calendrier", "calendar", "rdv", "rendez vous", "rendez-vous")):
        return UserIntent(
            name="calendar_read",
            confidence=0.84,
            summary="Lire les prochains evenements Google Calendar en lecture seule.",
        )

    if _has_any(text, ("gmail", "mes mails", "mes emails", "boite mail", "dernier mail", "dernier email")):
        if _has_any(text, ("repond", "reponse", "brouillon", "redige")):
            return UserIntent(
                name="gmail_reply_draft",
                confidence=0.86,
                summary="Lire Gmail en lecture seule et preparer un brouillon de reponse.",
            )
        return UserIntent(
            name="gmail_read",
            confidence=0.78,
            summary="Lire les derniers mails Gmail en lecture seule.",
        )

    if _has_any(
        text,
        (
            "nouveau projet",
            "nouvelle idee projet",
            "cree un projet",
            "creer un projet",
            "project factory",
        ),
    ):
        return UserIntent(
            name="project_factory",
            confidence=0.88,
            summary="Transformer une idee en workspace local, fichiers projet, prompt Cursor et Git/GitHub.",
        )

    if _has_any(text, ("cursor", "codex")):
        return UserIntent(
            name="cursor_work",
            confidence=0.76,
            summary="Preparer ou lancer une session de travail Cursor/Codex locale.",
        )

    if _has_any(text, ("doctor", "statut", "status", "actions en attente", "heartbeat", "obsidian")):
        return UserIntent(
            name="local_status",
            confidence=0.68,
            summary="Consulter l'etat local d'Eva ou un module interne.",
        )

    return UserIntent(
        name="generic_chat",
        confidence=0.45,
        summary="Conversation generale avec Eva.",
    )


def format_intent_context(intent: UserIntent) -> str:
    lines = [
        f"Interpretation Eva: {intent.summary}",
        f"Intent: {intent.name} ({round(intent.confidence * 100)}%)",
    ]
    if intent.caution:
        lines.append(f"Attention: {intent.caution}")
    return "\n".join(lines)
