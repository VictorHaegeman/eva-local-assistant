import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.security.action_policy import ActionPolicyLevel


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
SKILLS_EXAMPLE_PATH = DATA_DIR / "eva_skills.example.json"
SKILLS_PATH = DATA_DIR / "eva_skills.json"

SkillStatus = Literal["active", "candidate", "experimental", "planned"]
SkillSource = Literal["core", "local"]


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
    source: SkillSource = "core"
    status: SkillStatus = "active"
    extension_type: str = "prompt"
    requires: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    enabled: bool = True


SKILLS: tuple[SkillDescriptor, ...] = (
    SkillDescriptor(
        key="operator_planning",
        label="Boucle operateur",
        category="agents",
        policy_level="read_only",
        trigger_words=("fais", "ouvre", "cherche", "analyse", "cree", "lance", "trouve", "aide"),
        description="Interpreter la demande avant d'agir, puis executer le meilleur plan autorise.",
        instructions=(
            "Avant d'agir, comprends l'objectif reel, choisis la route d'action, verifie les risques, "
            "execute les outils autorises et rapporte le resultat concret. "
            "Ne stocke pas les consignes sur Eva comme souvenirs personnels."
        ),
        tool_hints=("action_planner",),
    ),
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
            "Lis les articles quand c'est possible, filtre selon Victor, puis sors uniquement "
            "l'important: 3 choses a savoir, 1 opportunite, 1 risque, 1 idee LinkedIn et 1 action. "
            "Distingue clairement faits, idees et actions proposees."
        ),
        tool_hints=("smart_brief", "heartbeat", "rss_brief"),
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


LOCAL_SKILL_CATALOG: tuple[dict[str, object], ...] = (
    {
        "key": "screen_autopilot",
        "label": "Autopilote ecran",
        "category": "desktop",
        "policy_level": "draft_only",
        "trigger_words": ["ecran", "pixels", "clique", "bouton", "interface", "fenetre"],
        "description": "Utiliser la vision locale pour comprendre l'ecran puis agir sur les boutons visibles.",
        "instructions": (
            "Avant un clic, lis l'ecran, identifie la fenetre active, le bouton cible et le risque. "
            "N'envoie pas de message externe sans validation explicite."
        ),
        "tool_hints": ["screen_reader", "visual_action", "desktop_automation"],
        "status": "experimental",
        "extension_type": "vision_toolflow",
        "requires": ["EVA_SCREEN_ENABLED=true", "modele vision Ollama"],
        "next_steps": ["ajouter OCR local", "ajouter detection de boutons plus robuste"],
        "enabled": True,
    },
    {
        "key": "operator_reflexes",
        "label": "Reflexes operateur",
        "category": "agents",
        "policy_level": "read_only",
        "trigger_words": ["autonome", "corrige", "resous", "solution", "reessaie", "probleme"],
        "description": "Relire le journal operateur pour proposer ou lancer une meilleure deuxieme tentative.",
        "instructions": (
            "Si une reponse precedente etait faible ou bloquee, consulte le journal operateur, "
            "reprends le reflexe note et tente un plan B autorise."
        ),
        "tool_hints": ["operator_journal", "understanding_layer", "terminal_doctor"],
        "status": "experimental",
        "extension_type": "reflection_loop",
        "requires": ["journal operateur actif"],
        "next_steps": ["auto-relance pour actions non critiques", "score de confiance par tentative"],
        "enabled": True,
    },
    {
        "key": "telegram_operator",
        "label": "Operateur Telegram",
        "category": "messaging",
        "policy_level": "draft_only",
        "trigger_words": ["telegram", "depuis mon telephone", "quand je suis pas chez moi", "iphone"],
        "description": "Interpreter les messages Telegram comme des taches longues avec contexte et updates.",
        "instructions": (
            "Utilise le contexte Telegram recent, garde les updates courts et dis ce qui est vraiment en cours. "
            "Pour les actions locales non critiques, agis si la session Telegram est autorisee."
        ),
        "tool_hints": ["telegram_remote", "operator_journal", "project_factory"],
        "status": "active",
        "extension_type": "remote_control",
        "requires": ["EVA_TELEGRAM_ENABLED=true", "EVA_TELEGRAM_ALLOWED_CHAT_ID"],
        "next_steps": ["updates de progression par tache longue", "queue de jobs Telegram"],
        "enabled": True,
    },
    {
        "key": "project_factory_operator",
        "label": "Project Factory autonome",
        "category": "code",
        "policy_level": "draft_only",
        "trigger_words": ["nouveau projet", "idee projet", "workspace", "github", "repo", "cursor"],
        "description": "Transformer une idee en workspace local, documents projet, repo GitHub et prompt Cursor.",
        "instructions": (
            "Transforme l'idee en brief, cree les fichiers projet autorises, prepare Cursor et garde une trace. "
            "Git push et actions critiques restent soumis aux flags de securite."
        ),
        "tool_hints": ["project_factory", "cursor_prompt", "local_command"],
        "status": "active",
        "extension_type": "workflow",
        "requires": ["Git", "GitHub CLI pour creation repo", "Cursor CLI optionnel"],
        "next_steps": ["suivi automatique des jobs Cursor", "audit post-generation"],
        "enabled": True,
    },
    {
        "key": "gmail_inbox_operator",
        "label": "Inbox Gmail intelligente",
        "category": "gmail",
        "policy_level": "draft_only",
        "trigger_words": ["gmail", "mail", "inbox", "dernier mail", "pas repondu", "brouillon"],
        "description": "Lire les vrais mails, auditer les fils sans reponse, creer des brouillons sans envoi.",
        "instructions": (
            "Lis le mail reel avant tout brouillon. Ne reponds pas aux alertes automatiques comme si elles etaient humaines. "
            "Ne dis jamais qu'un mail est envoye."
        ),
        "tool_hints": ["gmail_reply_draft", "google_calendar"],
        "status": "active",
        "extension_type": "connector",
        "requires": ["OAuth Gmail local", "scope gmail.readonly", "scope gmail.compose pour brouillons"],
        "next_steps": ["tri prioritaire", "creation calendrier apres validation"],
        "enabled": True,
    },
    {
        "key": "linkedin_growth_operator",
        "label": "LinkedIn Growth",
        "category": "business",
        "policy_level": "draft_only",
        "trigger_words": ["linkedin", "post", "contenu", "dreamlense", "prospect", "commentaire"],
        "description": "Proposer posts, commentaires et idees LinkedIn pour DreamLense sans publication automatique.",
        "instructions": (
            "Prepare des brouillons pertinents, premium et actionnables. Ne publie jamais sans validation humaine."
        ),
        "tool_hints": ["linkedin_draft", "linkedin_browser_bridge", "smart_brief"],
        "status": "active",
        "extension_type": "browser_bridge",
        "requires": ["session LinkedIn dans Brave pour ouverture navigateur"],
        "next_steps": ["score opportunite LinkedIn depuis Gmail", "calendrier editorial"],
        "enabled": True,
    },
    {
        "key": "voice_operator",
        "label": "Voix Eva",
        "category": "voice",
        "policy_level": "draft_only",
        "trigger_words": ["voix", "parle", "micro", "ok eva", "jarvis"],
        "description": "Piloter Eva a la voix avec wake word local et reponses vocales.",
        "instructions": (
            "Pour la voix, garder des confirmations courtes, lire les actions en cours et demander validation "
            "avant envoi/publication/suppression."
        ),
        "tool_hints": ["voice_control", "desktop_automation"],
        "status": "planned",
        "extension_type": "voice",
        "requires": ["wake word local", "STT local ou navigateur", "TTS local"],
        "next_steps": ["choisir moteur STT local", "ajouter push-to-talk desktop"],
        "enabled": False,
    },
    {
        "key": "mcp_gateway_candidate",
        "label": "Gateway MCP locale",
        "category": "extensions",
        "policy_level": "confirmation_required",
        "trigger_words": ["mcp", "extension", "plugin", "serveur local", "tools externes"],
        "description": "Future passerelle pour exposer des outils locaux sous forme de connecteurs standardises.",
        "instructions": (
            "Ne charge aucun serveur MCP inconnu automatiquement. Verifie les permissions, la source, "
            "les chemins autorises et le niveau de risque avant usage."
        ),
        "tool_hints": ["doctor", "action_policy"],
        "status": "candidate",
        "extension_type": "mcp",
        "requires": ["modele de permissions", "audit des outils", "allowlist"],
        "next_steps": ["catalogue de serveurs locaux fiables", "hash/schema des tools"],
        "enabled": False,
    },
)


def _write_example_skills_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "description": "Catalogue local de skills/extension Eva. Copie vers eva_skills.json pour personnaliser.",
        "skills": list(LOCAL_SKILL_CATALOG),
    }
    SKILLS_EXAMPLE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def ensure_skills_file() -> None:
    if not SKILLS_EXAMPLE_PATH.exists():
        _write_example_skills_file()

    if not SKILLS_PATH.exists():
        SKILLS_PATH.write_text(
            SKILLS_EXAMPLE_PATH.read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def _safe_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _safe_key(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", str(value).strip())[:80]


def _skill_from_payload(payload: dict[str, object]) -> SkillDescriptor | None:
    key = _safe_key(payload.get("key"))
    label = str(payload.get("label", "")).strip()[:120]
    if not key or not label:
        return None

    policy_level = str(payload.get("policy_level", "read_only")).strip()
    if policy_level not in {"read_only", "draft_only", "confirmation_required", "blocked"}:
        policy_level = "read_only"

    status = str(payload.get("status", "candidate")).strip()
    if status not in {"active", "candidate", "experimental", "planned"}:
        status = "candidate"

    return SkillDescriptor(
        key=key,
        label=label,
        category=str(payload.get("category", "extensions")).strip()[:80] or "extensions",
        policy_level=policy_level,  # type: ignore[arg-type]
        trigger_words=_safe_tuple(payload.get("trigger_words")),
        description=str(payload.get("description", "")).strip()[:600],
        instructions=str(payload.get("instructions", "")).strip()[:1600],
        tool_hints=_safe_tuple(payload.get("tool_hints")),
        source="local",
        status=status,  # type: ignore[arg-type]
        extension_type=str(payload.get("extension_type", "prompt")).strip()[:80] or "prompt",
        requires=_safe_tuple(payload.get("requires")),
        next_steps=_safe_tuple(payload.get("next_steps")),
        enabled=bool(payload.get("enabled", True)),
    )


def load_local_skills() -> tuple[SkillDescriptor, ...]:
    ensure_skills_file()
    try:
        payload = json.loads(SKILLS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()

    raw_skills = payload.get("skills") if isinstance(payload, dict) else None
    if not isinstance(raw_skills, list):
        return ()

    loaded: list[SkillDescriptor] = []
    for raw_skill in raw_skills:
        if not isinstance(raw_skill, dict):
            continue
        skill = _skill_from_payload(raw_skill)
        if skill:
            loaded.append(skill)
    return tuple(loaded)


def all_skills() -> tuple[SkillDescriptor, ...]:
    local_by_key = {skill.key: skill for skill in load_local_skills()}
    core = tuple(local_by_key.pop(skill.key, skill) for skill in SKILLS)
    return (*core, *local_by_key.values())


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
            "source": skill.source,
            "status": skill.status,
            "extension_type": skill.extension_type,
            "requires": list(skill.requires),
            "next_steps": list(skill.next_steps),
            "enabled": skill.enabled,
        }
        for skill in all_skills()
    ]


def _matches_skill(skill: SkillDescriptor, message: str) -> bool:
    normalized = message.lower()
    return any(trigger in normalized for trigger in skill.trigger_words)


def select_skills(message: str, limit: int = 4) -> list[SkillDescriptor]:
    skills = all_skills()
    matched = [skill for skill in skills if skill.enabled and _matches_skill(skill, message)]
    if matched:
        return matched[:limit]

    fallback_keys = {"operator_planning", "decision_partner", "personal_memory", "safety_guard"}
    return [skill for skill in skills if skill.key in fallback_keys][:limit]


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
