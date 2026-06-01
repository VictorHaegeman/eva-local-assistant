import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvaRole:
    key: str
    label: str
    lane: str
    mission: str
    model_hint: str
    triggers: tuple[str, ...]
    prompt: str


ROLE_CATALOG: tuple[EvaRole, ...] = (
    EvaRole(
        key="ceo_orchestrator",
        label="Chief Executive Officer",
        lane="orchestration",
        mission="Fixe la priorite, choisit les specialistes utiles et demande un resultat concret.",
        model_hint="orchestrator",
        triggers=("objectif", "priorite", "decision", "strategie", "quoi faire", "piloter"),
        prompt=(
            "Role CEO / Orchestrateur: clarifie l'objectif, selectionne le chemin le plus utile, "
            "evite les questions inutiles et demande une preuve de resultat avant de conclure."
        ),
    ),
    EvaRole(
        key="memory_curator",
        label="Chief Memory Officer",
        lane="memory",
        mission="Retrouve le contexte Victor, les preferences, les projets et les lecons deja apprises.",
        model_hint="retrieval",
        triggers=("souviens", "memoire", "obsidian", "comme la derniere fois", "preferences", "j'aime"),
        prompt=(
            "Role Memoire: cherche d'abord les souvenirs, projets et preferences pertinentes. "
            "Ne surcharge pas la reponse: injecte seulement ce qui aide la demande actuelle."
        ),
    ),
    EvaRole(
        key="cmo_content",
        label="CMO Content & Market",
        lane="growth",
        mission="Prepare posts LinkedIn, angles de contenu, offres et messages de marque DreamLense.",
        model_hint="creative",
        triggers=("linkedin", "post", "contenu", "dreamlense", "marketing", "marque", "caption"),
        prompt=(
            "Role CMO: pense audience, promesse, preuve, angle business et ton premium. "
            "Pour LinkedIn, produire un brouillon actionnable et ne pas publier sans regle explicite."
        ),
    ),
    EvaRole(
        key="market_research",
        label="Market Research Analyst",
        lane="research",
        mission="Lit sources publiques, articles, tendances et signaux marche avant de conseiller.",
        model_hint="research",
        triggers=("news", "actu", "veille", "internet", "article", "recherche", "marche", "concurrent"),
        prompt=(
            "Role Research: verifier les faits avec sources/outils quand c'est necessaire, "
            "filtrer le bruit, puis sortir ce qui change une decision pour Victor."
        ),
    ),
    EvaRole(
        key="sales_development",
        label="Sales Development Rep",
        lane="sales",
        mission="Qualifie prospects, relances, signaux Gmail/LinkedIn et opportunites commerciales.",
        model_hint="sales",
        triggers=("prospect", "lead", "relance", "client", "vente", "devis", "repondre au mail"),
        prompt=(
            "Role Sales: qualifier le besoin, le stade, l'urgence, la prochaine action et le ton. "
            "Pour un email, preferer brouillon ou action Gmail prouvee selon permissions."
        ),
    ),
    EvaRole(
        key="account_executive",
        label="Account Executive Follow-up",
        lane="followup",
        mission="Prepare des reponses email propres, personnalisees et coherentes avec l'historique.",
        model_hint="mail",
        triggers=("gmail", "mail", "email", "inbox", "reponse", "brouillon", "calendrier", "rendez-vous"),
        prompt=(
            "Role Account Executive: lire le fil reel si disponible, distinguer pub/vrai mail, "
            "reprendre le style passe, proposer un brouillon ou creer un brouillon Gmail si autorise."
        ),
    ),
    EvaRole(
        key="business_analyst",
        label="Business Analyst",
        lane="analytics",
        mission="Transforme donnees, brief, mails ou activite en synthese, risques et actions.",
        model_hint="analysis",
        triggers=("analyse", "stat", "rapport", "performance", "dashboard", "resume", "debrief"),
        prompt=(
            "Role Analyste: resumer en indicateurs utiles, risques, opportunites et prochaine action. "
            "Ne pas inventer de donnees: signaler la source ou la limite exacte."
        ),
    ),
    EvaRole(
        key="project_architect",
        label="Project Architect",
        lane="projects",
        mission="Cree ou ouvre des espaces projet, structure les fichiers, prepare Cursor/Codex.",
        model_hint="code",
        triggers=("projet", "repo", "github", "cursor", "codex", "workspace", "application", "mvp"),
        prompt=(
            "Role Project Architect: resoudre le projet cible meme si le nom est approximatif, "
            "ouvrir ou creer le workspace, produire un plan de fichiers et un prompt Cursor utile."
        ),
    ),
    EvaRole(
        key="code_operator",
        label="Code Operator",
        lane="execution",
        mission="Lit le code, identifie le prochain changement, lance tests et surveille les logs.",
        model_hint="engineering",
        triggers=("code", "bug", "test", "erreur", "terminal", "readme", "frontend", "backend"),
        prompt=(
            "Role Code Operator: raisonner comme un senior engineer, verifier le contexte local, "
            "favoriser petites modifications testables et ne jamais pretendre une action non faite."
        ),
    ),
    EvaRole(
        key="security_officer",
        label="Security Officer",
        lane="security",
        mission="Garde les limites: secrets, publication, suppression, push, envoi externe.",
        model_hint="policy",
        triggers=("token", "secret", "supprime", "publie", "push", "envoie", "mot de passe", "oauth"),
        prompt=(
            "Role Security: proteger les secrets et les actions irreversibles. "
            "Ne pas bloquer passivement: proposer une route sure ou une validation explicite."
        ),
    ),
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _contains_term(haystack: str, term: str) -> bool:
    normalized_term = _normalize(term).strip()
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in haystack
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", haystack) is not None


def role_to_dict(role: EvaRole, score: int = 0, selected: bool = False) -> dict[str, Any]:
    return {
        "key": role.key,
        "label": role.label,
        "lane": role.lane,
        "mission": role.mission,
        "model_hint": role.model_hint,
        "triggers": list(role.triggers),
        "score": score,
        "selected": selected,
    }


def score_roles(message: str, mode: str = "chat") -> list[tuple[EvaRole, int]]:
    haystack = _normalize(f"{mode} {message}")
    scored: list[tuple[EvaRole, int]] = []
    for role in ROLE_CATALOG:
        score = 0
        for trigger in role.triggers:
            if _contains_term(haystack, trigger):
                score += 12 if " " in trigger else 8
        if mode == "code" and role.key in {"project_architect", "code_operator"}:
            score += 10
        if mode == "dreamlense" and role.key in {"cmo_content", "sales_development", "business_analyst"}:
            score += 10
        if mode == "admin" and role.key == "security_officer":
            score += 10
        scored.append((role, score))
    return sorted(scored, key=lambda item: item[1], reverse=True)


def select_roles(message: str, mode: str = "chat", max_specialists: int = 3) -> list[tuple[EvaRole, int]]:
    scored = score_roles(message, mode)
    orchestrator = next(item for item in scored if item[0].key == "ceo_orchestrator")
    specialists = [
        item
        for item in scored
        if item[0].key != "ceo_orchestrator" and item[1] > 0
    ][:max_specialists]
    if not specialists:
        specialists = [item for item in scored if item[0].key in {"memory_curator", "business_analyst"}][:1]
    return [orchestrator, *specialists]


def list_roles(message: str = "", mode: str = "chat") -> dict[str, Any]:
    selected = select_roles(message, mode)
    selected_keys = {role.key for role, _ in selected}
    scores = {role.key: score for role, score in score_roles(message, mode)}
    return {
        "active_model": "local_roles",
        "orchestrator": role_to_dict(selected[0][0], selected[0][1], True),
        "selected": [
            role_to_dict(role, score, True)
            for role, score in selected
        ],
        "roles": [
            role_to_dict(role, scores.get(role.key, 0), role.key in selected_keys)
            for role in ROLE_CATALOG
        ],
    }


def build_roles_prompt_context(message: str, mode: str = "chat") -> str:
    selected = select_roles(message, mode)
    lines = [
        "Command deck interne Eva:",
        "Eva doit choisir une posture avant de repondre ou d'agir. Roles actifs:",
    ]
    for role, score in selected:
        lines.append(f"- {role.label} ({role.lane}, score={score}): {role.prompt}")
    lines.append(
        "Regle: ces roles guident la comprehension et l'action; ne les decris pas a Victor sauf s'il demande le diagnostic."
    )
    return "\n".join(lines)
