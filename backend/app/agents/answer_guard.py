import re


FAKE_ACTION_PATTERNS = (
    r"\bje vais (?:essayer d')?(?:ouvrir|charger|afficher|lancer)\b",
    r"\bj'ai (?:ouvert|charge|chargé|affiche|affiché|lance|lancé)\b",
    r"\bvoici l'adresse url que j'ai (?:chargee|chargée|ouverte)\b",
    r"\bje suis connecte au pc de victor\b",
    r"\bje suis connecté au pc de victor\b",
    r"\bnavigateur par defaut\b",
    r"\bnavigateur par défaut\b",
)

GENERIC_CLOSING_PATTERNS = (
    r"\n*\s*(?:pouvez-vous|peux-tu|dites-moi|dis-moi|n'hesitez pas|n’hésitez pas).{0,180}(?:autre chose|quelque chose d'autre|si vous souhaitez|si tu souhaites|besoin d'aide|questions?)\s*[?.!]*\s*$",
    r"\n*\s*(?:souhaitez-vous|veux-tu|voulez-vous).{0,180}(?:autre chose|que je fasse|continuer|la suite)\s*[?.!]*\s*$",
)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _strip_generic_closing(answer: str) -> str:
    cleaned = answer.rstrip()
    for pattern in GENERIC_CLOSING_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL).rstrip()
    return cleaned or answer.strip()


def _contains_fake_action_claim(answer: str) -> bool:
    normalized = _normalize(answer)
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in FAKE_ACTION_PATTERNS)


def _likely_action_domain(user_message: str) -> str:
    normalized = _normalize(user_message)
    if any(marker in normalized for marker in ("projet", "cursor", "codex", "repo", "code")):
        return "projet"
    if any(marker in normalized for marker in ("mail", "gmail", "email")):
        return "gmail"
    if any(marker in normalized for marker in ("youtube", "video", "site", "web", "navigateur", "brave")):
        return "web"
    if any(marker in normalized for marker in ("spotify", "musique", "playlist")):
        return "spotify"
    return "action"


def guard_ollama_answer(answer: str, user_message: str) -> str:
    """Keep fallback LLM answers grounded when no explicit tool returned a result."""

    cleaned = _strip_generic_closing(answer)
    if not _contains_fake_action_claim(cleaned):
        return cleaned

    domain = _likely_action_domain(user_message)
    if domain == "projet":
        return (
            "Je corrige: je n'ai pas de preuve qu'un navigateur ou un site ait ete ouvert dans ce tour. "
            "Pour cette demande, je dois d'abord resoudre le projet local vise, ouvrir/preparer Cursor, "
            "puis rapporter seulement le resultat reel de l'outil."
        )
    if domain == "gmail":
        return (
            "Je corrige: je n'ai pas de preuve qu'un mail reel ait ete ouvert ou lu dans ce tour. "
            "Pour Gmail, je dois utiliser l'API Gmail locale ou dire clairement que la connexion manque."
        )
    if domain == "web":
        return (
            "Je corrige: je n'ai pas de preuve qu'une page web ait ete ouverte dans ce tour. "
            "Je ne dois pas inventer d'URL; je dois utiliser l'outil navigateur/recherche puis donner le resultat reel."
        )
    if domain == "spotify":
        return (
            "Je corrige: je n'ai pas de preuve que Spotify ait ete ouvert ou que la musique joue. "
            "Je dois utiliser l'outil Spotify local et rapporter uniquement ce qui a ete tente."
        )

    return (
        "Je corrige: je n'ai pas de preuve qu'une action locale ait ete executee dans ce tour. "
        "Je dois utiliser un outil local disponible ou expliquer la limite exacte, sans inventer."
    )
