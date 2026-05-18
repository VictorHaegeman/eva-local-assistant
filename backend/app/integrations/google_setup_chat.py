import unicodedata
from pathlib import Path

from app.integrations.browser import open_url
from app.integrations.gmail_auth import GmailAuthLaunchError, start_gmail_oauth_flow
from app.integrations.gmail_client import gmail_status
from app.integrations.google_calendar_client import calendar_status, list_calendar_events


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GMAIL_AUTH_SCRIPT = PROJECT_ROOT / "backend" / "app" / "integrations" / "gmail_auth.py"
GOOGLE_CLOUD_CREDENTIALS_URL = "https://console.cloud.google.com/apis/credentials"
GOOGLE_CLOUD_OAUTH_CONSENT_URL = "https://console.cloud.google.com/apis/credentials/consent"


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def wants_google_account_setup(message: str) -> bool:
    normalized = _normalize(message)
    google_markers = ("google", "gmail", "oauth", "mail", "mails", "calendar", "calendrier")
    action_markers = (
        "connect",
        "connexion",
        "compte",
        "script",
        "autorisation",
        "authentification",
        "acces",
        "accede",
        "lire",
        "lis",
        "va sur internet",
        "va sur mon compte",
    )
    return any(marker in normalized for marker in google_markers) and any(
        marker in normalized for marker in action_markers
    )


def wants_calendar_events(message: str) -> bool:
    normalized = _normalize(message)
    calendar_markers = ("agenda", "calendrier", "calendar", "rdv", "rendez vous", "rendez-vous")
    read_markers = ("quoi", "voir", "lis", "lire", "aujourd", "semaine", "prochains", "planning")
    return any(marker in normalized for marker in calendar_markers) and any(
        marker in normalized for marker in read_markers
    )


def build_calendar_events_response(days: int = 7) -> str:
    events = list_calendar_events(days=days, max_results=10)
    if not events:
        return f"Aucun evenement trouve dans ton calendrier principal sur les {days} prochains jours."

    lines = [f"Voici les prochains evenements Google Calendar sur {days} jours:"]
    for event in events:
        when = event.start or "date inconnue"
        location = f" - {event.location}" if event.location else ""
        lines.append(f"- {when}: {event.summary}{location}")
    return "\n".join(lines)


def build_google_setup_response(
    trusted_actions: bool = False,
    intent_context: str = "",
) -> str:
    gmail = gmail_status()
    calendar = calendar_status()
    lines = []
    if intent_context:
        lines.extend([intent_context, ""])

    lines.extend([
        "J'ai trouve la brique locale Google dans Eva.",
        "",
        f"Script OAuth: {GMAIL_AUTH_SCRIPT}",
        f"Credentials attendus: {gmail['credentials_path']}",
        f"Token local: {gmail['token_path']}",
        "",
        "Acces prevus:",
        "- Gmail: lecture seule;",
        "- Calendar: lecture seule;",
        "- aucun envoi mail;",
        "- aucune modification calendrier;",
        "- aucun mot de passe stocke dans Eva.",
        "",
        "Etat actuel:",
        f"- Gmail active: {gmail['enabled']}",
        f"- JSON OAuth present: {gmail['credentials_exists']}",
        f"- token local present: {gmail['token_exists']}",
        f"- scopes requis OK: {gmail['token_has_required_scopes']}",
    ])

    missing_scopes = gmail.get("missing_scopes") or calendar.get("missing_scopes") or []
    if missing_scopes:
        lines.append(f"- scopes manquants: {', '.join(str(scope) for scope in missing_scopes)}")

    if not trusted_actions:
        lines.extend(
            [
                "",
                "Depuis une session non fiable je ne lance pas OAuth. Fais-le depuis ton PC local ou ton Telegram autorise.",
            ]
        )
        return "\n".join(lines)

    if not gmail["credentials_exists"]:
        open_url(GOOGLE_CLOUD_CREDENTIALS_URL)
        open_url(GOOGLE_CLOUD_OAUTH_CONSENT_URL)
        lines.extend(
            [
                "",
                "J'ai ouvert Google Cloud dans Brave.",
                "Action humaine requise:",
                "1. Va dans ton projet Google Cloud.",
                "2. Configure l'ecran de consentement OAuth et ajoute ton Gmail en test user.",
                "3. Cree un client OAuth de type Desktop app.",
                "4. Telecharge le JSON complet.",
                "5. Place-le dans data/gmail_credentials.json.",
                "6. Redemande a Eva: connecte mon compte Google.",
            ]
        )
        return "\n".join(lines)

    try:
        result = start_gmail_oauth_flow(force_reconnect=not gmail["token_has_required_scopes"])
    except GmailAuthLaunchError as exc:
        lines.extend(["", f"Je n'ai pas pu lancer OAuth: {exc}"])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            str(result.get("message", "Flux OAuth Google lance.")),
            "Valide le compte dans la page Google ouverte. Ensuite Eva pourra lire Gmail et Calendar en lecture seule.",
        ]
    )
    return "\n".join(lines)
