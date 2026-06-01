import unicodedata
from pathlib import Path

from app.integrations.browser import open_url
from app.integrations.gmail_auth import GmailAuthLaunchError, start_gmail_oauth_flow
from app.integrations.gmail_client import gmail_status
from app.integrations.google_calendar_client import calendar_status, list_calendar_events


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GMAIL_AUTH_SCRIPT = PROJECT_ROOT / "backend" / "app" / "integrations" / "gmail_auth.py"
GOOGLE_CLOUD_CREDENTIALS_URL = "https://console.cloud.google.com/auth/clients"
GOOGLE_CLOUD_OAUTH_AUDIENCE_URL = "https://console.cloud.google.com/auth/audience"


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _public_invalid_token_reason(reason: object) -> str:
    normalized = _normalize(str(reason))
    if "invalid_grant" in normalized or "expired" in normalized or "revoked" in normalized:
        return "expire ou revoque par Google"
    if "scope" in normalized:
        return "scopes Google incomplets"
    if normalized:
        return "token local invalide"
    return "token local invalide"


def wants_google_account_setup(message: str) -> bool:
    normalized = _normalize(message)
    google_markers = ("google", "gmail", "oauth", "calendar", "calendrier", "compte google")
    troubleshooting_markers = (
        "casse",
        "cassee",
        "cassé",
        "cassée",
        "marche pas",
        "ne marche pas",
        "ne fonctionne pas",
        "fonctionne pas",
        "bug",
        "bloque",
        "bloquee",
        "panne",
        "pourquoi",
        "failed",
        "erreur",
        "erreur gmail",
        "gmail indisponible",
        "indisponible",
        "token absent",
        "invalid grant",
        "invalid_grant",
        "reconnecte",
        "reconnecter",
        "reconnexion",
        "ne lit pas",
        "ne lis pas",
    )
    if any(marker in normalized for marker in google_markers) and any(
        marker in normalized for marker in troubleshooting_markers
    ):
        return True

    explicit_setup_markers = (
        "connect",
        "connexion",
        "autorisation",
        "authentification",
        "oauth",
        "credentials",
        "credential",
        "token",
        "script oauth",
        "json oauth",
        "client oauth",
    )
    if not any(marker in normalized for marker in explicit_setup_markers):
        return False

    action_markers = (
        "connect",
        "connexion",
        "script",
        "autorisation",
        "authentification",
        "acces",
        "accede",
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
        return (
            "Source: Google Calendar API, lecture seule.\n"
            f"Aucun evenement trouve dans ton calendrier principal sur les {days} prochains jours."
        )

    lines = [
        "Source: Google Calendar API, lecture seule.",
        f"Voici les prochains evenements reels renvoyes par Google Calendar sur {days} jours:",
    ]
    for event in events:
        when = event.start or "date inconnue"
        location = f" - {event.location}" if event.location else ""
        lines.append(f"- {when}: {event.summary}{location}")
    return "\n".join(lines)


def build_google_setup_response(
    trusted_actions: bool = False,
    intent_context: str = "",
    force_reconnect: bool = False,
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
        "- Gmail: lecture + creation de brouillons;",
        "- Calendar: lecture seule;",
        "- aucun envoi mail automatique;",
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

    if gmail.get("last_invalid_token_reason"):
        lines.append(f"- dernier token invalide: {_public_invalid_token_reason(gmail['last_invalid_token_reason'])}")
    elif gmail.get("last_invalid_token"):
        lines.append("- dernier token invalide detecte localement.")

    if gmail["credentials_exists"] and not gmail["token_exists"]:
        lines.append("- diagnostic: credentials presents, mais token Google local absent.")

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
        open_url(GOOGLE_CLOUD_OAUTH_AUDIENCE_URL)
        lines.extend(
            [
                "",
                "J'ai ouvert Google Cloud dans Brave.",
                "Action humaine requise:",
                "1. Va dans ton projet Google Cloud.",
                "2. Ouvre Google Auth Platform > Audience > Test users.",
                "3. Ajoute ton adresse Gmail comme utilisateur test.",
                "4. Verifie que Gmail API et Google Calendar API sont activees.",
                "5. Cree un client OAuth de type Desktop app.",
                "6. Telecharge le JSON complet.",
                "7. Place-le dans data/gmail_credentials.json.",
                "8. Redemande a Eva: connecte mon compte Google.",
            ]
        )
        return "\n".join(lines)

    if not gmail["token_exists"]:
        lines.extend(
            [
                "",
                "Je vais relancer le flux OAuth local. Si Google affiche 403 access_denied, alors il faudra ouvrir Google Auth Platform > Audience et ajouter ton Gmail dans Test users.",
            ]
        )

    try:
        result = start_gmail_oauth_flow(
            force_reconnect=force_reconnect or not gmail["token_has_required_scopes"]
        )
    except GmailAuthLaunchError as exc:
        lines.extend(["", f"Je n'ai pas pu lancer OAuth: {exc}"])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            str(result.get("message", "Flux OAuth Google lance.")),
            "Valide le compte dans la page Google ouverte. Ensuite Eva pourra lire Gmail, creer des brouillons Gmail et lire Calendar.",
        ]
    )
    return "\n".join(lines)
