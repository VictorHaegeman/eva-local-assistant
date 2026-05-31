import re
import unicodedata
from dataclasses import dataclass

from app.memory.memory_store import Memory


@dataclass(frozen=True)
class MemoryCluster:
    key: str
    label: str
    description: str
    keywords: tuple[str, ...]
    categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClusterRoute:
    cluster: MemoryCluster
    score: float


CLUSTERS: tuple[MemoryCluster, ...] = (
    MemoryCluster(
        key="victor_identity",
        label="Victor / identite",
        description="Infos stables sur Victor: nom, email, role, contexte personnel.",
        keywords=("victor", "email", "nom", "identite", "profil", "signature"),
        categories=("identity",),
    ),
    MemoryCluster(
        key="dreamlense",
        label="DreamLense",
        description="Projet DreamLense, business, offres, clients, contenus et prospects.",
        keywords=("dreamlense", "portrait", "portraits", "sas", "prospect", "linkedin", "business"),
        categories=("project",),
    ),
    MemoryCluster(
        key="writing_preferences",
        label="Preferences redaction",
        description="Style de redaction, mails, signature, ton, formats preferes.",
        keywords=("redige", "redaction", "mail", "email", "signature", "style", "ton", "cordial"),
        categories=("preference",),
    ),
    MemoryCluster(
        key="eva_operating_rules",
        label="Regles comportement Eva",
        description="Lecons de comportement, interpretation, autonomie et maniere d'agir.",
        keywords=("eva", "agir", "action", "autonomie", "reflechir", "interprete", "outil", "bouton"),
        categories=("operating_rule",),
    ),
    MemoryCluster(
        key="gmail_calendar",
        label="Gmail / Calendar",
        description="Mails, calendrier, rendez-vous, suivi inbox et brouillons.",
        keywords=("gmail", "mail", "mails", "email", "emails", "inbox", "thread", "calendar", "calendrier", "rdv", "rendez-vous"),
    ),
    MemoryCluster(
        key="housing",
        label="Gmail / appartements",
        description="Recherche immobiliere, annonces, appartements, visites et loyers.",
        keywords=("appartement", "location", "bienici", "pap", "loyer", "immobilier", "visite"),
    ),
    MemoryCluster(
        key="code_projects",
        label="Projets code",
        description="Repos, Cursor, Codex, bugs, README, branches, PR et architecture.",
        keywords=("code", "projet", "projets", "repo", "github", "cursor", "codex", "bug", "readme", "branche", "pr"),
        categories=("project",),
    ),
    MemoryCluster(
        key="project_factory",
        label="Project Factory",
        description="Creation de projets, workspace, repo GitHub, prompts Cursor et sessions de codage.",
        keywords=("nouveau projet", "projet", "projets", "project factory", "workspace", "github", "repo", "cursor-agent", "cursor", "codex"),
        categories=("workflow", "project"),
    ),
    MemoryCluster(
        key="frontend_design",
        label="Design / frontend",
        description="Direction artistique, interface Jarvis-like, animation, UI, UX et preferences visuelles.",
        keywords=("frontend", "design", "interface", "ui", "ux", "jarvis", "premium", "animation", "hud", "bleu", "cyan"),
        categories=("preference", "creation", "design"),
    ),
    MemoryCluster(
        key="screen_navigation",
        label="Vision / ecran",
        description="Lecture des pixels, navigation locale, clics visuels, fenetres, boutons et verification ecran.",
        keywords=("ecran", "screen", "pixels", "clique", "bouton", "fenetre", "navigation", "brave", "spotify", "youtube"),
        categories=("screen_navigation", "operating_rule"),
    ),
    MemoryCluster(
        key="content_social",
        label="Contenu / social",
        description="Posts LinkedIn, DreamLense, angles de contenu, copywriting et activite sociale.",
        keywords=("linkedin", "post", "contenu", "copywriting", "dreamlense", "commentaire", "activite", "reseau"),
        categories=("content", "preference"),
    ),
    MemoryCluster(
        key="learning_feedback",
        label="Apprentissage / feedback",
        description="Corrections de Victor, erreurs repetees, frustrations et regles apprises.",
        keywords=("corrige", "erreur", "frustre", "comprends rien", "apprends", "feedback", "pas normal", "reflechis"),
        categories=("operating_rule", "idea"),
    ),
    MemoryCluster(
        key="messages",
        label="Beeper / messages",
        description="Messages, Beeper, Telegram, WhatsApp et reponses a preparer.",
        keywords=("beeper", "telegram", "whatsapp", "message", "repondre", "conversation"),
    ),
)


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.lower().strip().split())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_-]{3,}", _normalize(text)))


def list_memory_clusters() -> list[dict[str, object]]:
    return [
        {
            "key": cluster.key,
            "label": cluster.label,
            "description": cluster.description,
            "keywords": list(cluster.keywords),
            "categories": list(cluster.categories),
        }
        for cluster in CLUSTERS
    ]


def get_memory_cluster(key: str) -> MemoryCluster | None:
    for cluster in CLUSTERS:
        if cluster.key == key:
            return cluster
    return None


def route_memory_clusters(query: str, limit: int = 4) -> list[ClusterRoute]:
    query_tokens = _tokens(query)
    normalized = _normalize(query)
    routes: list[ClusterRoute] = []

    for cluster in CLUSTERS:
        keyword_hits = sum(
            1
            for keyword in cluster.keywords
            if _normalize(keyword) in normalized or _normalize(keyword) in query_tokens
        )
        if keyword_hits:
            score = min(1.0, keyword_hits / max(len(cluster.keywords), 1) + 0.25)
            routes.append(ClusterRoute(cluster=cluster, score=score))

    return sorted(routes, key=lambda route: route.score, reverse=True)[: max(1, limit)]


def infer_memory_cluster(memory: Memory) -> str:
    haystack = f"{memory.category} {memory.source} {memory.content}"
    routes = route_memory_clusters(haystack, limit=1)
    if routes:
        return routes[0].cluster.key

    normalized_category = _normalize(memory.category)
    for cluster in CLUSTERS:
        if normalized_category in {_normalize(category) for category in cluster.categories}:
            return cluster.key

    return "general"


def cluster_label(key: str) -> str:
    for cluster in CLUSTERS:
        if cluster.key == key:
            return cluster.label
    return "General"
