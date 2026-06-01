import re
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
    "cursor_agent_setup",
    "cursor_work",
    "local_status",
    "browser_or_video",
    "spotify",
    "desktop_control",
    "beeper_messages",
    "linkedin_activity",
    "linkedin_browser_post",
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


def _has_mail_word(text: str) -> bool:
    return bool(re.search(r"\b(?:mail|mails|mial|mials|meil|meils|email|emails|emial|emials|e-mail|e-mails|gmail)\b", text))


def _has_project_word(text: str) -> bool:
    return bool(re.search(r"\b(?:projet|projets|repo|repository|workspace)\b", text))


def _has_reply_context(text: str) -> bool:
    if re.search(r"\b(?:reponds?|repondre|reponse|brouillon|redige|ecris|ecrit|prepare)\b", text):
        return True
    return _has_any(
        text,
        (
            "pret a etre envoye",
            "pret a envoyer",
            "a approuver",
            "bouton repondre",
        ),
    )


def _has_reply_audit_context(text: str) -> bool:
    if re.search(r"\b(?:pas|jamais)\b.{0,40}\brepondu\b", text):
        return True
    if re.search(r"\b(?:non|sans)\b.{0,20}\b(?:repondu|reponse)\b", text):
        return True
    if re.search(r"\b(?:mails?|emails?)\b.{0,80}\ba\b.{0,20}\b(?:traiter|repondre)\b", text):
        return True
    if re.search(r"\b(?:mails?|emails?)\b.{0,90}\b(?:qui sont|auxquels?|que je dois)\b.{0,30}\b(?:repondre|traiter)\b", text):
        return True
    return _has_any(
        text,
        (
            "pas repondu",
            "pas encore repondu",
            "non repondu",
            "non-repondu",
            "sans reponse",
            "sans repondre",
            "a repondre",
            "a traiter",
            "que j'ai pas repondu",
            "que je n'ai pas repondu",
            "auxquels j'ai pas encore repondu",
            "auxquels je n'ai pas encore repondu",
            "qui sont a repondre",
            "qui sont a traiter",
            "mails a repondre",
            "mail a repondre",
        ),
    )


NEWS_MARKERS = (
    "news",
    "actu",
    "actus",
    "actualite",
    "actualites",
    "nouvelles",
    "quoi de neuf",
    "dernieres nouvelles",
    "dernieres actus",
    "dernieres infos",
    "ce qui se passe",
)


def has_news_context(text: str) -> bool:
    if _has_any(text, ("gmail", "mail", "mails", "email", "emails", "calendar", "calendrier")) and _has_any(
        text,
        (
            "casse",
            "cassee",
            "marche pas",
            "ne marche pas",
            "ne fonctionne pas",
            "bug",
            "erreur",
            "panne",
            "reconnecte",
            "reconnecter",
        ),
    ):
        return False
    return _has_any(text, NEWS_MARKERS)


def _looks_like_new_project_request(text: str) -> bool:
    if _has_any(
        text,
        (
            "project factory",
            "nouveau projet",
            "nouvelle idee projet",
            "nouvelle idee de projet",
            "idee de projet",
            "j'ai une idee de projet",
            "jai une idee de projet",
            "j'ai une nouvelle idee",
            "jai une nouvelle idee",
        ),
    ):
        return True

    create_markers = (
        "cree",
        "creer",
        "crée",
        "lance",
        "demarre",
        "prepare",
        "monte",
        "setup",
        "scaffold",
        "initialise",
    )
    target_markers = (
        "projet",
        "repo",
        "repository",
        "workspace",
        "application",
        "app",
        "saas",
        "site",
        "outil",
        "mvp",
    )
    if re.search(
        r"\b(?:cree|creer|crÃ©e|lance|demarre|prepare|monte|setup|scaffold|initialise)\b",
        text,
    ) and re.search(
        r"\b(?:projet|repo|repository|workspace|application|app|saas|site|outil|mvp)\b",
        text,
    ):
        return True

    return bool(
        re.search(
            r"\b(?:nouvelle?|nouveau|new)\b.{0,40}\b(?:idee|idée|projet|app|saas|repo)\b",
            text,
        )
    )


def classify_user_intent(message: str) -> UserIntent:
    text = normalize_intent_text(message)

    if has_news_context(text):
        return UserIntent(
            name="web_search",
            confidence=0.88,
            summary=(
                "Donner des nouvelles recentes: chercher l'actualite utile et ne pas reutiliser "
                "le contexte d'une action precedente."
            ),
        )

    if _has_any(text, ("cursor-agent", "cursor agent", "agent cursor", "cursor cli")) and _has_any(
        text,
        (
            "installe",
            "installer",
            "install",
            "setup",
            "configure",
            "configurer",
            "active",
            "activer",
            "mettre en place",
            "pour tous les projets",
            "tous les projets",
        ),
    ):
        return UserIntent(
            name="cursor_agent_setup",
            confidence=0.94,
            summary=(
                "Installer ou activer Cursor Agent CLI globalement sur le PC pour permettre "
                "l'execution autonome sur les projets."
            ),
            caution=(
                "Cursor Agent s'installe officiellement via macOS, Linux ou Windows WSL; "
                "sur Windows natif il faut verifier WSL."
            ),
        )

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
            "eteins mon pc",
            "eteint mon pc",
            "eteindre mon pc",
            "arrete mon pc",
            "arrette mon pc",
            "shutdown mon pc",
            "shutdown pc",
            "redemarre mon pc",
            "restart mon pc",
            "mets mon pc en veille",
            "met mon pc en veille",
        ),
    ):
        return UserIntent(
            name="desktop_control",
            confidence=0.92,
            summary=(
                "Interpreter une demande d'alimentation PC comme action locale Windows, "
                "pas comme recherche web."
            ),
            caution="Extinction/redemarrage/veille sont des actions systeme critiques a traiter par politique locale.",
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
            "navigue sur mon ecran",
            "navigue dans l'ecran",
            "pilote mon ecran",
            "utilise mon ecran",
            "regarde l'ecran et",
            "regarde mon ecran et",
            "trouve le bouton",
            "clique sur le bon bouton",
            "remplis le champ",
            "remplis le formulaire",
        ),
    ):
        return UserIntent(
            name="screen_read",
            confidence=0.9,
            summary="Lire les pixels de l'ecran local et interpreter ce qui est visible.",
            caution="La capture reste locale et peut contenir des donnees privees.",
        )

    gmail_context = _has_mail_word(text) or _has_any(
        text,
        ("gmail", "mes mails", "mes emails", "boite mail", "dernier mail", "dernier email", "le mail", "ce mail", "au mail", "mails"),
    )
    reply_audit_context = _has_reply_audit_context(text)
    if gmail_context and reply_audit_context:
        return UserIntent(
            name="gmail_reply_audit",
            confidence=0.9,
            summary="Lire les mails reels correspondant au sujet demande et verifier ceux sans reponse de Victor.",
        )

    if gmail_context and _has_reply_context(text):
        return UserIntent(
            name="gmail_reply_draft",
            confidence=0.91,
            summary="Lire le mail reel, ouvrir le fil Gmail si demande, puis preparer une reponse basee sur les mails envoyes de Victor.",
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
            "casse",
            "cassee",
            "marche pas",
            "ne marche pas",
            "ne fonctionne pas",
            "bug",
            "erreur",
            "panne",
            "reconnecte",
            "reconnecter",
            "reconnexion",
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

    if _has_any(text, ("beeper", "message beeper", "messages beeper", "mes messages")) and "linkedin" not in text:
        return UserIntent(
            name="beeper_messages",
            confidence=0.82,
            summary="Ouvrir ou lire Beeper via le pont local/vision selon la demande.",
        )

    if "linkedin" in text and _has_any(
        text,
        (
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
            "invitations",
            "commentaires",
            "likes",
            "statistiques",
            "stats",
            "nouveaux",
            "nouvelles",
        ),
    ):
        return UserIntent(
            name="linkedin_activity",
            confidence=0.87,
            summary=(
                "Lire les signaux LinkedIn disponibles localement, surtout via les notifications Gmail, "
                "sans preparer ni publier de post."
            ),
        )

    if "linkedin" in text and _has_any(
        text,
        (
            "post",
            "contenu",
            "commentaire",
            "publie",
            "publier",
            "poster",
            "ouvre",
            "ouvrir",
            "dreamlense",
            "redige",
            "ecris",
            "idee",
        ),
    ):
        return UserIntent(
            name="linkedin_browser_post",
            confidence=0.86,
            summary=(
                "Preparer un contenu LinkedIn pertinent, ouvrir LinkedIn et remplir le brouillon "
                "sans publication automatique."
            ),
        )

    if _looks_like_new_project_request(text):
        return UserIntent(
            name="project_factory",
            confidence=0.92,
            summary=(
                "Transformer une idee en workspace local, fichiers projet, prompt Cursor, Git/GitHub "
                "et lancement agent autonome si disponible."
            ),
        )

    project_work_context = _has_project_word(text) and _has_any(
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
            "ameliore",
            "ameliorer",
            "optimise",
            "optimiser",
            "code",
            "coder",
            "prompt",
            "prompts",
            "cursor",
            "codex",
        ),
    )
    if project_work_context:
        return UserIntent(
            name="cursor_work",
            confidence=0.86,
            summary=(
                "Identifier le projet local vise, meme avec un nom approximatif, "
                "puis ouvrir/preparer une session de travail Cursor."
            ),
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
            "brave",
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

    reply_context = _has_reply_context(text)
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
