from dataclasses import dataclass

from app.security.action_policy import ActionPolicyLevel


@dataclass(frozen=True)
class ToolDescriptor:
    key: str
    label: str
    category: str
    policy_level: ActionPolicyLevel
    description: str
    enabled: bool = True


TOOLS = (
    ToolDescriptor(
        key="ollama_chat",
        label="Ollama Chat",
        category="llm",
        policy_level="read_only",
        description="Reponses IA locales via Ollama.",
    ),
    ToolDescriptor(
        key="memory_store",
        label="Memoire locale",
        category="memory",
        policy_level="read_only",
        description="Lecture et ajout prudent de souvenirs non sensibles.",
    ),
    ToolDescriptor(
        key="obsidian_memory",
        label="Obsidian Memory",
        category="memory",
        policy_level="read_only",
        description="Miroir Markdown local des souvenirs Eva dans un vault Obsidian ignore par Git.",
    ),
    ToolDescriptor(
        key="skills_registry",
        label="Skills Eva",
        category="skills",
        policy_level="read_only",
        description="Catalogue local de competences qui oriente les reponses d'Eva.",
    ),
    ToolDescriptor(
        key="file_read",
        label="Lecture fichiers",
        category="files",
        policy_level="read_only",
        description="Lecture texte dans les dossiers autorises.",
    ),
    ToolDescriptor(
        key="web_search",
        label="Recherche web",
        category="web",
        policy_level="read_only",
        description="Recherche web gratuite sans API payante.",
    ),
    ToolDescriptor(
        key="cursor_prompt",
        label="Prompt Cursor",
        category="code",
        policy_level="draft_only",
        description="Preparation de prompts Cursor/Codex sans appel OpenAI par Eva.",
    ),
    ToolDescriptor(
        key="project_factory",
        label="Project Factory",
        category="code",
        policy_level="confirmation_required",
        description="Prepare un workspace, un prompt Cursor et des actions locales a valider.",
    ),
    ToolDescriptor(
        key="gmail_reply_draft",
        label="Brouillon Gmail",
        category="gmail",
        policy_level="draft_only",
        description="Brouillon de reponse email, aucun envoi automatique.",
    ),
    ToolDescriptor(
        key="linkedin_draft",
        label="LinkedIn",
        category="linkedin",
        policy_level="draft_only",
        description="Idees, posts et commentaires LinkedIn en brouillon uniquement.",
    ),
    ToolDescriptor(
        key="heartbeat",
        label="Heartbeat",
        category="automation",
        policy_level="read_only",
        description="Taches locales planifiees et controles de routine.",
    ),
    ToolDescriptor(
        key="local_command",
        label="Commande locale",
        category="system",
        policy_level="confirmation_required",
        description="Commande Windows locale avec validation humaine.",
    ),
    ToolDescriptor(
        key="write_file",
        label="Ecriture fichier",
        category="files",
        policy_level="confirmation_required",
        description="Modification de fichier avec validation humaine.",
    ),
)


def list_tools() -> list[dict[str, object]]:
    return [
        {
            "key": tool.key,
            "label": tool.label,
            "category": tool.category,
            "policy_level": tool.policy_level,
            "description": tool.description,
            "enabled": tool.enabled,
        }
        for tool in TOOLS
    ]
