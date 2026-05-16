from dataclasses import dataclass

from app.security.action_policy import ActionPolicyLevel


@dataclass(frozen=True)
class SkillDescriptor:
    key: str
    label: str
    category: str
    policy_level: ActionPolicyLevel
    trigger_words: tuple[str, ...]
    description: str
    instructions: str
    tool_hints: tuple[str, ...] = ()
    enabled: bool = True


SKILLS: tuple[SkillDescriptor, ...] = (
    SkillDescriptor(
        key="personal_memory",
        label="Memoire personnelle",
        category="memory",
        policy_level="read_only",
        trigger_words=("retiens", "souviens", "memorise", "memoire", "preference"),
        description="Retenir et utiliser des informations non sensibles sur Victor.",
        instructions=(
            "Utilise le profil et les memoires locales quand c'est utile. "
            "Les souvenirs peuvent etre miroires dans le vault Obsidian local pour relecture. "
            "Ne stocke jamais de mot de passe, token, cle API ou secret. "
            "Si Victor dit clairement de retenir une information non sensible, confirme que c'est note."
        ),
        tool_hints=("memory_store", "obsidian_memory"),
    ),
    SkillDescriptor(
        key="project_operator",
        label="Assistant projets code",
        category="code",
        policy_level="draft_only",
        trigger_words=("projet", "repo", "cursor", "codex", "bug", "readme", "pr"),
        description="Analyser les projets locaux connus et preparer du travail pour Cursor/Codex.",
        instructions=(
            "Quand Victor parle d'un projet, aide a cadrer le travail, identifier les fichiers, "
            "preparer un prompt Cursor/Codex, une checklist ou un plan de PR. "
            "Ne dis jamais qu'un fichier, une branche ou une PR a ete creee si ce n'est pas execute et valide."
        ),
        tool_hints=("project_context", "cursor_prompt"),
    ),
    SkillDescriptor(
        key="dreamlense_growth",
        label="DreamLense growth",
        category="business",
        policy_level="draft_only",
        trigger_words=("dreamlense", "prospect", "business", "linkedin", "offre", "client"),
        description="Aider Victor sur marketing, offres, ventes et contenus DreamLense.",
        instructions=(
            "Oriente les reponses vers des actions concretes: angle, cible, message, objection, "
            "prochaine etape. Garde un ton clair, direct, premium et professionnel."
        ),
        tool_hints=("linkedin_draft", "gmail_reply_draft"),
    ),
    SkillDescriptor(
        key="email_drafter",
        label="Redaction email",
        category="communication",
        policy_level="draft_only",
        trigger_words=("mail", "email", "gmail", "reponse", "relance", "signature"),
        description="Rediger des emails et brouillons en respectant le style et la signature.",
        instructions=(
            "Redige des brouillons relisibles par Victor. Utilise la signature locale si pertinente. "
            "Ne pretends jamais avoir envoye un email. L'envoi demande une validation humaine."
        ),
        tool_hints=("gmail_reply_draft",),
    ),
    SkillDescriptor(
        key="morning_brief",
        label="Brief du matin",
        category="brief",
        policy_level="read_only",
        trigger_words=("brief", "matin", "actu", "veille", "rss", "news"),
        description="Structurer l'actualite et les sources en brief utile.",
        instructions=(
            "Structure en sections: business, tech, IA, finance, DreamLense, opportunites, priorites. "
            "Distingue clairement faits, idees et actions proposees."
        ),
        tool_hints=("heartbeat", "rss_brief"),
    ),
    SkillDescriptor(
        key="local_research",
        label="Recherche locale et web",
        category="research",
        policy_level="read_only",
        trigger_words=("cherche", "recherche", "analyse", "resume", "source", "document"),
        description="Lire les contenus autorises et faire des recherches web gratuites.",
        instructions=(
            "Synthetise les informations avec prudence. Si la source manque ou si l'information peut etre recente, "
            "dis ce qui est verifie et ce qui reste a confirmer."
        ),
        tool_hints=("file_read", "web_search"),
    ),
    SkillDescriptor(
        key="decision_partner",
        label="Decision partner",
        category="thinking",
        policy_level="read_only",
        trigger_words=("decision", "choisir", "strategie", "priorite", "plan", "organise"),
        description="Aider Victor a clarifier une decision, une priorite ou un plan.",
        instructions=(
            "Reponds avec options, criteres, compromis et recommandation courte. "
            "Evite le blabla et termine avec une prochaine action concrete."
        ),
    ),
    SkillDescriptor(
        key="safety_guard",
        label="Garde-fou actions",
        category="security",
        policy_level="confirmation_required",
        trigger_words=("commande", "supprime", "modifie", "push", "publie", "envoie"),
        description="Appliquer les validations humaines sur les actions sensibles.",
        instructions=(
            "Avant toute commande systeme, modification, suppression, git push, publication, envoi de mail "
            "ou usage actif d'un compte externe, demande ou cree une validation humaine explicite."
        ),
        tool_hints=("action_policy", "actions"),
    ),
)


def list_skills() -> list[dict[str, object]]:
    return [
        {
            "key": skill.key,
            "label": skill.label,
            "category": skill.category,
            "policy_level": skill.policy_level,
            "trigger_words": list(skill.trigger_words),
            "description": skill.description,
            "instructions": skill.instructions,
            "tool_hints": list(skill.tool_hints),
            "enabled": skill.enabled,
        }
        for skill in SKILLS
    ]


def _matches_skill(skill: SkillDescriptor, message: str) -> bool:
    normalized = message.lower()
    return any(trigger in normalized for trigger in skill.trigger_words)


def select_skills(message: str, limit: int = 4) -> list[SkillDescriptor]:
    matched = [skill for skill in SKILLS if skill.enabled and _matches_skill(skill, message)]
    if matched:
        return matched[:limit]

    fallback_keys = {"decision_partner", "personal_memory", "safety_guard"}
    return [skill for skill in SKILLS if skill.key in fallback_keys][:limit]


def build_skills_prompt_context(message: str) -> str:
    skills = select_skills(message)
    lines = [
        "Skills Eva disponibles pour orienter la reponse.",
        "Une skill est une consigne de comportement, pas une preuve qu'une action a ete executee.",
    ]

    for skill in skills:
        tool_hints = ", ".join(skill.tool_hints) if skill.tool_hints else "aucun tool requis"
        lines.append(
            f"- {skill.label} [{skill.policy_level}] ({skill.category}): "
            f"{skill.instructions} Tools utiles: {tool_hints}."
        )

    return "\n".join(lines)
