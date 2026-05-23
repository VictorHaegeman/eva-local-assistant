import unicodedata
from dataclasses import dataclass
from typing import Literal


IntentName = Literal[
    "terminal_error",
    "screen_read",
    "google_oauth_setup",
    "calendar_read",
    "gmail_read",
    "gmail_reply_audit",
    "gmail_reply_draft",
    "project_factory",
    "cursor_work",
    "local_status",
    "browser_or_video",
    "spotify",
    "desktop_control",
    "beeper_messages",
    "web_search",
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

    gmail_context = _has_any(
        text,
        ("gmail", "mes mails", "mes emails", "boite mail", "dernier mail", "dernier email", "le mail", "ce mail", "au mail", "mails"),
    )
    reply_audit_context = _has_any(
        text,
        (
            "pas repondu",
            "non repondu",
            "sans reponse",
            "sans repondre",
            "a repondre",
            "a traiter",
            "que j'ai pas repondu",
            "que je n'ai pas repondu",
        ),
    )
    if gmail_context and reply_audit_context:
        return UserIntent(
            name="gmail_reply_audit",
            confidence=0.9,
            summary="Lire les mails reels correspondant au sujet demande et verifier ceux sans reponse de Victor.",
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

    if _has_any(text, ("spotify", "musique", "playlist", "lance une chanson", "mets ")):
        return UserIntent(
            name="spotify",
            confidence=0.86,
            summary="Ouvrir Spotify ou lancer une recherche musicale locale selon la demande.",
        )

    if _has_any(text, ("beeper", "message beeper", "messages beeper", "mes messages")):
        return UserIntent(
            name="beeper_messages",
            confidence=0.82,
            summary="Ouvrir ou lire Beeper via le pont local/vision selon la demande.",
        )

    if _has_any(text, ("clique", "click", "appuie", "presse", "touche", "play", "pause")):
        return UserIntent(
            name="desktop_control",
            confidence=0.8,
            summary="Interagir avec l'interface locale ou envoyer une commande clavier/souris sure.",
            caution="Les actions visuelles doivent etre verifiees par capture locale quand elles sont ambigues.",
        )

    if _has_any(
        text,
        (
            "youtube",
            "video",
            "tuto",
            "tutoriel",
            "carte",
            "cartz",
            "map",
            "maps",
            "google maps",
            "google earth",
            "ouvre brave",
            "ouvre le navigateur",
            "ouvre google",
            "ouvre un onglet",
            "site web",
        ),
    ):
        return UserIntent(
            name="browser_or_video",
            confidence=0.82,
            summary="Ouvrir le bon site, une carte ou une video dans Brave apres interpretation de la demande.",
        )

    if _has_any(
        text,
        (
            "cherche sur internet",
            "recherche internet",
            "va sur internet",
            "trouve sur internet",
            "cherche web",
            "recherche web",
        ),
    ):
        return UserIntent(
            name="web_search",
            confidence=0.84,
            summary="Faire une recherche web gratuite puis filtrer les resultats utiles.",
        )

    reply_context = _has_any(
        text,
        (
            "repond",
            "reponse",
            "brouillon",
            "redige",
            "ecris",
            "ecrit",
            "pret a etre envoye",
            "pret a envoyer",
            "a approuver",
            "bouton repondre",
        ),
    )
    if gmail_context:
        if reply_context:
            return UserIntent(
                name="gmail_reply_draft",
                confidence=0.86,
                summary="Lire le mail reel, rediger une reponse et creer un brouillon Gmail si le scope compose est autorise.",
            )
        return UserIntent(
            name="gmail_read",
            confidence=0.78,
            summary="Lire les derniers mails Gmail reels via l'API Google.",
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

    project_work_context = _has_any(text, ("projet", "repo", "repository", "workspace")) and _has_any(
        text,
        (
            "bosser",
            "travaille",
            "travailler",
            "reprends",
            "reprendre",
            "continue",
            "ouvrir",
            "ouvre",
            "lance",
            "switch",
            "bascule",
            "retourne",
        ),
    )
    if project_work_context:
        return UserIntent(
            name="cursor_work",
            confidence=0.82,
            summary=(
                "Identifier le projet local vise, meme avec un nom approximatif, "
                "puis ouvrir/preparer une session de travail Cursor."
            ),
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
